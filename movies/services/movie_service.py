"""
Movie Service - Handles all movie-related business logic
"""
import requests
import logging
import time
import random
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from django.conf import settings
from django.core.cache import cache
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)


class MovieService:
    """Service class for handling movie-related operations"""
    
    def __init__(self):
        self.tmdb_base_url = "https://api.themoviedb.org/3"
        self.tmdb_api_key = settings.TMDB_API_KEY
        self.session = self._create_requests_session()
    
    def _create_requests_session(self) -> requests.Session:
        """Create a requests session with retry capability"""
        session = requests.Session()
        
        retries = Retry(
            total=5,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def _make_tmdb_request(self, endpoint: str, params: Optional[Dict] = None, 
                          cache_timeout: int = 3600) -> Dict[str, Any]:
        """Make a request to TMDB API with caching and error handling"""
        if params is None:
            params = {}
        
        params['api_key'] = self.tmdb_api_key
        cache_key = f"tmdb_{endpoint}_{str(params)}"
        
        # Try to get from cache first
        cached_response = cache.get(cache_key)
        if cached_response is not None:
            return cached_response
        
        # Not in cache, make the request
        url = f"{self.tmdb_base_url}{endpoint}"
        
        try:
            time.sleep(random.uniform(0.1, 0.3))
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            cache.set(cache_key, data, timeout=cache_timeout)
            return data
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error for {endpoint}: {e}")
            self.session = self._create_requests_session()
            raise
        except Exception as e:
            logger.error(f"Error for {endpoint}: {e}")
            raise
    
    def get_movie(self, movie_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific movie"""
        try:
            cache_key = f"movie_details_{movie_id}"
            movie = cache.get(cache_key)
            
            if movie is not None:
                return movie
            
            endpoint = f"/movie/{movie_id}"
            params = {'append_to_response': 'credits,videos,recommendations'}
            
            movie_data = self._make_tmdb_request(endpoint, params, cache_timeout=86400)
            
            movie = self._process_movie_data(movie_data)
            cache.set(cache_key, movie, timeout=86400)
            
            return movie
            
        except Exception as e:
            logger.error(f"Error fetching movie {movie_id}: {e}")
            return None
    
    def _process_movie_data(self, movie_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process raw movie data from TMDB API"""
        release_date = movie_data.get('release_date', '')
        
        movie = {
            'id': movie_data['id'],
            'title': movie_data['title'],
            'overview': movie_data.get('overview', ''),
            'release_date': release_date,
            'runtime': movie_data.get('runtime', 0),
            'vote_average': movie_data.get('vote_average', 0),
            'vote_count': movie_data.get('vote_count', 0),
            'genres': [genre['name'] for genre in movie_data.get('genres', [])],
            'poster_url': f"https://image.tmdb.org/t/p/w500{movie_data['poster_path']}" if movie_data.get('poster_path') else None,
            'backdrop_url': f"https://image.tmdb.org/t/p/original{movie_data['backdrop_path']}" if movie_data.get('backdrop_path') else None,
            'tagline': movie_data.get('tagline', ''),
            'status': movie_data.get('status', ''),
            'budget': movie_data.get('budget', 0),
            'revenue': movie_data.get('revenue', 0),
            'original_language': movie_data.get('original_language', ''),
            'production_companies': [company['name'] for company in movie_data.get('production_companies', [])],
            'production_countries': [country['name'] for country in movie_data.get('production_countries', [])],
        }
        
        # Add formatted date
        if release_date:
            try:
                from datetime import datetime
                date_obj = datetime.strptime(release_date, '%Y-%m-%d')
                movie['release_date_formatted'] = date_obj.strftime('%d-%m-%Y')
            except Exception as e:
                logger.warning(f"Could not format date {release_date}: {e}")
                movie['release_date_formatted'] = release_date
        
        # Process cast information
        movie['cast'] = self._process_cast(movie_data.get('credits', {}).get('cast', []))
        movie['first_cast'] = movie['cast'][0] if movie['cast'] else None
        
        # Process crew information
        crew = movie_data.get('credits', {}).get('crew', [])
        movie['directors'] = self._process_directors(crew)
        movie['writers'] = self._process_writers(crew)
        
        # Process trailer information
        movie['trailer_key'] = self._get_trailer_key(movie_data, movie['id'])
        
        # Process recommendations
        movie['recommendations'] = self._process_recommendations(movie_data.get('recommendations', {}).get('results', []))
        
        return movie
    
    def _process_cast(self, cast_data: List[Dict]) -> List[Dict]:
        """Process cast data to include only actors with profile images"""
        cast = []
        for actor in cast_data[:20]:
            if actor.get('profile_path'):
                cast_member = {
                    'id': actor['id'],
                    'name': actor['name'],
                    'character': actor.get('character', ''),
                    'profile_path': actor.get('profile_path')
                }
                cast.append(cast_member)
                if len(cast) >= 10:
                    break
        return cast
    
    def _process_directors(self, crew: List[Dict]) -> List[Dict]:
        """Process crew data to extract directors"""
        directors = []
        for crew_member in crew:
            if crew_member.get('job') == 'Director':
                directors.append({
                    'id': crew_member['id'],
                    'name': crew_member['name'],
                    'profile_path': crew_member.get('profile_path')
                })
        return directors
    
    def _process_writers(self, crew: List[Dict]) -> List[Dict]:
        """Process crew data to extract writers"""
        writers = []
        for crew_member in crew:
            if crew_member.get('department') == 'Writing':
                writers.append({
                    'id': crew_member['id'],
                    'name': crew_member['name'],
                    'job': crew_member.get('job', ''),
                    'profile_path': crew_member.get('profile_path')
                })
        return writers
    
    def _get_trailer_key(self, movie_data: Dict, movie_id: int) -> Optional[str]:
        """Extract trailer key from movie data"""
        videos = movie_data.get('videos', {}).get('results', [])
        
        if not videos:
            try:
                videos_data = self._make_tmdb_request(f"/movie/{movie_id}/videos", cache_timeout=86400)
                videos = videos_data.get('results', [])
            except Exception as e:
                logger.error(f"Error fetching videos for movie {movie_id}: {e}")
                videos = []
        
        # Look for official trailers first
        for video in videos:
            if (video.get('site') == 'YouTube' and 
                video.get('type') == 'Trailer' and 
                video.get('official', True) and
                video.get('key')):
                return video.get('key')
        
        # Fallback to any trailer
        for video in videos:
            if video.get('site') == 'YouTube' and video.get('type') == 'Trailer' and video.get('key'):
                return video.get('key')
        
        # Fallback to teasers
        for video in videos:
            if video.get('site') == 'YouTube' and video.get('type') == 'Teaser' and video.get('key'):
                return video.get('key')
        
        # Fallback to any YouTube video
        for video in videos:
            if video.get('site') == 'YouTube' and video.get('key'):
                return video.get('key')
        
        return None
    
    def _process_recommendations(self, recommendations: List[Dict]) -> List[Dict]:
        """Process recommendations data"""
        processed_recs = []
        for rec in recommendations[:6]:
            if rec.get('poster_path'):
                poster_url = f"https://image.tmdb.org/t/p/w500{rec['poster_path']}"
            else:
                poster_url = None
                
            processed_recs.append({
                'id': rec['id'],
                'title': rec['title'],
                'poster_url': poster_url,
                'vote_average': rec.get('vote_average', 0)
            })
        return processed_recs
    
    def get_popular_movies(self, page: int = 1, limit: int = 20) -> List[Dict[str, Any]]:
        """Get a list of popular movies"""
        try:
            endpoint = "/movie/popular"
            params = {'page': page}
            
            data = self._make_tmdb_request(endpoint, params, cache_timeout=3600)
            
            movies = []
            for movie in data.get('results', [])[:limit]:
                movies.append(self._format_movie_summary(movie))
            
            return movies
            
        except Exception as e:
            logger.error(f"Error fetching popular movies: {e}")
            return []
    
    def get_trending_movies(self, time_window: str = 'week', page: int = 1) -> List[Dict[str, Any]]:
        """Get trending movies for the day or week"""
        try:
            endpoint = f"/trending/movie/{time_window}"
            params = {'page': page}
            
            data = self._make_tmdb_request(endpoint, params, cache_timeout=3600)
            
            movies = []
            for movie in data.get('results', []):
                movies.append(self._format_movie_summary(movie))
            
            return movies
            
        except Exception as e:
            logger.error(f"Error fetching trending movies: {e}")
            return []
    
    def search_movies(self, query: str, page: int = 1) -> List[Dict[str, Any]]:
        """Search for movies by title"""
        try:
            endpoint = "/search/movie"
            params = {
                'query': query,
                'page': page,
                'include_adult': 'false'
            }
            
            data = self._make_tmdb_request(endpoint, params, cache_timeout=3600)
            
            results = []
            for movie in data.get('results', []):
                movie_data = self._format_movie_summary(movie)
                # Add genres
                genres = []
                for genre_id in movie.get('genre_ids', []):
                    genre_name = self.get_genre_name(genre_id)
                    if genre_name:
                        genres.append(genre_name)
                movie_data['genres'] = genres
                movie_data['original_language'] = movie.get('original_language', '')
                results.append(movie_data)
            
            return results
        except Exception as e:
            logger.error(f"Error searching movies: {e}")
            return []
    
    def get_actor_details(self, actor_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed information about an actor"""
        try:
            cache_key = f"actor_details_{actor_id}"
            actor = cache.get(cache_key)
            if actor is not None:
                return actor

            endpoint = f"/person/{actor_id}"
            params = {'append_to_response': 'images'}
            data = self._make_tmdb_request(endpoint, params, cache_timeout=86400)

            actor = {
                'id': data['id'],
                'name': data['name'],
                'biography': data.get('biography', ''),
                'birthday': data.get('birthday'),
                'deathday': data.get('deathday'),
                'place_of_birth': data.get('place_of_birth'),
                'profile_url': f"https://image.tmdb.org/t/p/w500{data['profile_path']}" if data.get('profile_path') else None,
                'known_for_department': data.get('known_for_department'),
                'gender': data.get('gender'),
                'popularity': data.get('popularity')
            }

            # Process images
            images = []
            for image in data.get('images', {}).get('profiles', [])[:10]:
                images.append({
                    'file_path': f"https://image.tmdb.org/t/p/w500{image['file_path']}",
                    'aspect_ratio': image.get('aspect_ratio', 0),
                    'height': image.get('height', 0),
                    'width': image.get('width', 0)
                })
            actor['images'] = images

            cache.set(cache_key, actor, timeout=86400)
            return actor

        except Exception as e:
            logger.error(f"Error fetching actor {actor_id}: {e}")
            return None
    
    def get_actor_movies(self, actor_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        """Get movies featuring a specific actor"""
        try:
            cache_key = f"actor_movies_{actor_id}"
            movies = cache.get(cache_key)
            
            if movies is not None:
                return movies
            
            endpoint = f"/person/{actor_id}/movie_credits"
            data = self._make_tmdb_request(endpoint, cache_timeout=86400)
            
            movies = []
            for movie in data.get('cast', []):
                movie_data = self._format_movie_summary(movie)
                movie_data['character'] = movie.get('character', '')
                movies.append(movie_data)
            
            cache.set(cache_key, movies, timeout=86400)
            return movies
            
        except Exception as e:
            logger.error(f"Error fetching movies for actor {actor_id}: {e}")
            return []
    
    def _format_movie_summary(self, movie: Dict[str, Any]) -> Dict[str, Any]:
        """Format movie data for summary display"""
        return {
            'id': movie['id'],
            'title': movie['title'],
            'poster_url': f"https://image.tmdb.org/t/p/w500{movie['poster_path']}" if movie.get('poster_path') else None,
            'release_date': movie.get('release_date', ''),
            'vote_average': movie.get('vote_average', 0),
            'overview': movie.get('overview', '')
        }
    
    def get_genre_name(self, genre_id: int) -> Optional[str]:
        """Convert genre ID to genre name"""
        genre_map = {
            28: 'Action', 12: 'Adventure', 16: 'Animation', 35: 'Comedy',
            80: 'Crime', 99: 'Documentary', 18: 'Drama', 10751: 'Family',
            14: 'Fantasy', 36: 'History', 27: 'Horror', 10402: 'Music',
            9648: 'Mystery', 10749: 'Romance', 878: 'Science Fiction',
            10770: 'TV Movie', 53: 'Thriller', 10752: 'War', 37: 'Western'
        }
        return genre_map.get(genre_id)
    
    def get_genre_id(self, genre_name: str) -> Optional[int]:
        """Convert genre name to genre ID"""
        genre_map = {
            'Action': 28, 'Adventure': 12, 'Animation': 16, 'Comedy': 35,
            'Crime': 80, 'Documentary': 99, 'Drama': 18, 'Family': 10751,
            'Fantasy': 14, 'History': 36, 'Horror': 27, 'Music': 10402,
            'Mystery': 9648, 'Romance': 10749, 'Science Fiction': 878,
            'TV Movie': 10770, 'Thriller': 53, 'War': 10752, 'Western': 37
        }
        return genre_map.get(genre_name)
