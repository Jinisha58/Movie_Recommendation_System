"""
Recommendation Service - Handles all recommendation-related business logic
"""
import logging
from typing import List, Dict, Optional, Any
from django.core.cache import cache
from django.conf import settings
from .movie_service import MovieService
from ..repositories.ratings_repository import RatingsRepository
from ..repositories.watchlist_repository import WatchlistRepository
from ..repositories.viewed_movies_repository import ViewedMoviesRepository

logger = logging.getLogger(__name__)


class RecommendationService:
    """Service class for handling recommendation algorithms"""
    
    def __init__(self,
                 ratings_repo: RatingsRepository | None = None,
                 watchlist_repo: WatchlistRepository | None = None,
                 viewed_repo: ViewedMoviesRepository | None = None):
        self.movie_service = MovieService()
        self.ratings_repo = ratings_repo or RatingsRepository()
        self.watchlist_repo = watchlist_repo or WatchlistRepository()
        self.viewed_repo = viewed_repo or ViewedMoviesRepository()
    
    def get_genres(self) -> Dict[int, str]:
        """Get all available genres from TMDB"""
        try:
            cache_key = "tmdb_genres"
            genres = cache.get(cache_key)
            
            if genres is None:
                import requests
                url = f"https://api.themoviedb.org/3/genre/movie/list?api_key={settings.TMDB_API_KEY}&language=en-US"
                res = requests.get(url).json()
                genres = {g['id']: g['name'] for g in res['genres']}
                cache.set(cache_key, genres, timeout=86400)
            
            return genres
        except Exception as e:
            logger.error(f"Error getting genres: {e}")
            return {}
    
    def get_movie_with_genres(self, movie_id: int) -> Optional[Dict[str, Any]]:
        """Get movie details including genre IDs"""
        try:
            import requests
            url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={settings.TMDB_API_KEY}&language=en-US"
            res = requests.get(url).json()
            
            if 'id' not in res:
                return None
                
            return {
                "id": res['id'],
                "name": res['title'],
                "genres": [g['id'] for g in res.get('genres', [])],
                "poster_path": res.get('poster_path'),
                "release_date": res.get('release_date', ''),
                "vote_average": res.get('vote_average', 0),
                "overview": res.get('overview', '')
            }
        except Exception as e:
            logger.error(f"Error getting movie {movie_id}: {e}")
            return None
    
    def get_popular_movies_with_genres(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get popular movies with their genre information"""
        try:
            import requests
            url = f"https://api.themoviedb.org/3/movie/popular?api_key={settings.TMDB_API_KEY}&language=en-US&page=1"
            res = requests.get(url).json()
            
            movies = []
            for m in res.get('results', [])[:limit]:
                movies.append({
                    "id": m['id'],
                    "name": m['title'],
                    "genres": m.get('genre_ids', []),
                    "poster_path": m.get('poster_path'),
                    "release_date": m.get('release_date', ''),
                    "vote_average": m.get('vote_average', 0),
                    "overview": m.get('overview', '')
                })
            
            return movies
        except Exception as e:
            logger.error(f"Error getting popular movies: {e}")
            return []
    
    def assign_movie_vectors(self, movies: List[Dict], all_genre_ids: List[int]) -> List[Dict]:
        """Assign genre vectors to movies"""
        for movie in movies:
            vector = [1 if gid in movie['genres'] else 0 for gid in all_genre_ids]
            movie['vector'] = vector
        return movies
    
    def cosine_similarity(self, movie1: Dict, movie2: Dict) -> float:
        """Calculate cosine similarity between two movies based on their genre vectors"""
        if 'vector' not in movie1 or 'vector' not in movie2:
            return 0
            
        dot_product = sum(a*b for a, b in zip(movie1['vector'], movie2['vector']))
        magnitude1 = sum(a**2 for a in movie1['vector']) ** 0.5
        magnitude2 = sum(b**2 for b in movie2['vector']) ** 0.5
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0
        
        return dot_product / (magnitude1 * magnitude2)
    
    def get_cosine_similarity_recommendations(self, user_movie_ids: List[int], 
                                            num_recommendations: int = 20) -> List[Dict[str, Any]]:
        """Get recommendations based on user's movie history using cosine similarity"""
        try:
            if not user_movie_ids:
                return []
            
            # Get genres
            genre_dict = self.get_genres()
            all_genre_ids = list(genre_dict.keys())
            
            if not all_genre_ids:
                logger.error("Could not fetch genres")
                return []
            
            # Get user's movies with genres
            user_movies = []
            for movie_id in user_movie_ids[:10]:  # Limit to first 10 movies
                movie = self.get_movie_with_genres(movie_id)
                if movie:
                    user_movies.append(movie)
            
            if not user_movies:
                return []
            
            # Get popular movies for comparison
            popular_movies = self.get_popular_movies_with_genres(limit=200)
            if not popular_movies:
                logger.error("Could not fetch popular movies")
                return []
            
            # Combine all movies and assign vectors
            all_movies = user_movies + popular_movies
            all_movies = self.assign_movie_vectors(all_movies, all_genre_ids)
            
            # Calculate average similarity for each popular movie
            movie_scores = {}
            user_movie_vectors = [m for m in all_movies if m['id'] in user_movie_ids]
            popular_movie_vectors = [m for m in all_movies if m['id'] not in user_movie_ids]
            
            for popular_movie in popular_movie_vectors:
                total_similarity = 0
                for user_movie in user_movie_vectors:
                    similarity = self.cosine_similarity(user_movie, popular_movie)
                    total_similarity += similarity
                
                avg_similarity = total_similarity / len(user_movie_vectors)
                movie_scores[popular_movie['id']] = avg_similarity
            
            # Sort by similarity score
            sorted_movies = sorted(movie_scores.items(), key=lambda x: x[1], reverse=True)
            top_movies = sorted_movies[:num_recommendations]
            
            # Convert to template format
            recommendations = []
            for movie_id, score in top_movies:
                movie = next((m for m in popular_movie_vectors if m['id'] == movie_id), None)
                if movie:
                    recommendations.append({
                        'id': movie['id'],
                        'title': movie['name'],
                        'poster_url': f"https://image.tmdb.org/t/p/w500{movie['poster_path']}" if movie['poster_path'] else None,
                        'release_date': movie['release_date'],
                        'vote_average': movie['vote_average'],
                        'overview': movie['overview'],
                        'similarity_score': round(score, 3)
                    })
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error getting cosine similarity recommendations: {e}")
            return []
    
    def get_recommendations_from_ratings(self, user_id: int, min_similarity: float = 0.5, 
                                       limit: int = 20) -> List[Dict[str, Any]]:
        """Recommend movies based on user's high ratings using genre vectors and cosine similarity"""
        try:
            # Fetch highly-rated movies by the user
            high_ratings = [r for r in self.ratings_repo.find_by_user(user_id) if int(r.get('rating', 0)) >= 4]

            if not high_ratings:
                return []

            # Genres universe
            genre_dict = self.get_genres()
            all_genre_ids = list(genre_dict.keys())
            if not all_genre_ids:
                return []

            # Get user's rated movies with genres
            user_movies = []
            for r in high_ratings:
                m = self.get_movie_with_genres(r['movie_id'])
                if m:
                    user_movies.append(m)

            if not user_movies:
                return []

            # Candidate pool: popular movies
            popular_movies = self.get_popular_movies_with_genres(limit=300)
            if not popular_movies:
                return []

            # Remove movies already rated by the user
            rated_ids = { m['id'] for m in user_movies }
            candidates = [m for m in popular_movies if m['id'] not in rated_ids]

            # Assign vectors
            all_movies = user_movies + candidates
            all_movies = self.assign_movie_vectors(all_movies, all_genre_ids)

            # Split back
            user_movie_vectors = [m for m in all_movies if m['id'] in rated_ids]
            candidate_vectors = [m for m in all_movies if m['id'] not in rated_ids]

            # Score candidates by average similarity to all user rated movies
            scored = []
            for cand in candidate_vectors:
                total = 0.0
                for um in user_movie_vectors:
                    total += self.cosine_similarity(um, cand)
                avg = total / len(user_movie_vectors)
                if avg >= min_similarity:
                    scored.append((cand, avg))

            # Sort by score desc and take top limit
            scored.sort(key=lambda x: x[1], reverse=True)
            scored = scored[:limit]

            # Convert to template format with similarity score
            results = []
            for movie, score in scored:
                results.append({
                    'id': movie['id'],
                    'title': movie['name'],
                    'poster_url': f"https://image.tmdb.org/t/p/w500{movie['poster_path']}" if movie['poster_path'] else None,
                    'release_date': movie['release_date'],
                    'vote_average': movie['vote_average'],
                    'overview': movie['overview'],
                    'similarity_score': round(float(score), 3)
                })

            return results
        except Exception as e:
            logger.error(f"Error in get_recommendations_from_ratings for user {user_id}: {e}")
            return []
    
    def get_global_featured(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Compute globally featured movies by combining TMDB popularity with engagement signals"""
        try:
            # Candidate pool
            candidates = self.movie_service.get_popular_movies(page=1, limit=200)
            if not candidates:
                return []

            featured_scored = []
            for m in candidates:
                movie_id = m.get('id')
                if not movie_id:
                    continue

                try:
                    views = self.viewed_repo.count_by_movie(movie_id)
                except Exception:
                    views = 0
                try:
                    wl = self.watchlist_repo.count_by_movie(movie_id)
                except Exception:
                    wl = 0
                try:
                    rc = self.ratings_repo.count_by_movie(movie_id)
                    avg_sum = 0
                    if rc > 0:
                        for r in self.ratings_repo.iter_by_movie(movie_id):
                            avg_sum += int(r.get('rating', 0))
                        avg_rating = avg_sum / max(rc, 1)
                    else:
                        avg_rating = 0
                except Exception:
                    rc = 0
                    avg_rating = 0

                # Score: base on TMDB vote_average; add engagement weights
                tmdb_score = float(m.get('vote_average', 0))
                score = tmdb_score * 1.0 + views * 0.05 + wl * 0.1 + rc * 0.1 + avg_rating * 0.2

                featured_scored.append((m, score))

            featured_scored.sort(key=lambda x: x[1], reverse=True)
            featured = [x[0] for x in featured_scored[:limit]]
            return featured
        except Exception as e:
            logger.error(f"Error computing global featured: {e}")
            return []
    
    def get_featured_for_user(self, user_id: int, limit: int = 12) -> List[Dict[str, Any]]:
        """Personalized featured using ratings-based cosine similarity as core content filter"""
        try:
            # Reuse ratings-based recommender as content core
            recs = self.get_recommendations_from_ratings(user_id, min_similarity=0.0, limit=limit)
            return recs[:limit]
        except Exception as e:
            logger.error(f"Error computing featured for user {user_id}: {e}")
            return []

    # New: genre-preference based recommendations
    def get_recommendations_by_genres(self, selected_genre_ids: List[int], limit: int = 20) -> List[Dict[str, Any]]:
        """Recommend movies that best match the user's selected genres using cosine similarity.

        selected_genre_ids: list of TMDB genre IDs the user checked.
        """
        try:
            # Guard
            selected_ids = [int(g) for g in selected_genre_ids if str(g).isdigit()]
            if not selected_ids:
                return []

            # Universe of genres
            genre_dict = self.get_genres()
            all_genre_ids = list(genre_dict.keys())
            if not all_genre_ids:
                return []

            # Candidate pool: popular movies with genre_ids
            candidates = self.get_popular_movies_with_genres(limit=300)
            if not candidates:
                return []

            # Assign vectors to candidates
            candidates = self.assign_movie_vectors(candidates, all_genre_ids)

            # Build preference vector (like a pseudo-movie)
            preference = {
                'vector': [1 if gid in selected_ids else 0 for gid in all_genre_ids]
            }

            # Score candidates by cosine similarity to the preference vector
            scored: List[tuple[Dict[str, Any], float]] = []
            for cand in candidates:
                score = self.cosine_similarity(preference, cand)
                scored.append((cand, score))

            # Sort and take top N
            scored.sort(key=lambda x: x[1], reverse=True)
            top = scored[:limit]

            # Convert to template format
            results: List[Dict[str, Any]] = []
            for cand, score in top:
                results.append({
                    'id': cand['id'],
                    'title': cand['name'],
                    'poster_url': f"https://image.tmdb.org/t/p/w500{cand['poster_path']}" if cand.get('poster_path') else None,
                    'release_date': cand.get('release_date', ''),
                    'vote_average': cand.get('vote_average', 0),
                    'overview': cand.get('overview', ''),
                    'similarity_score': round(float(score), 3)
                })

            return results
        except Exception as e:
            logger.error(f"Error getting recommendations by genres: {e}")
            return []