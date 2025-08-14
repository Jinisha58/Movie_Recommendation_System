import requests
from django.conf import settings
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)

TMDB_API_KEY = settings.TMDB_API_KEY

# ---------- Step 1: Get all genres from TMDB ----------
def get_genres():
    """Get all available genres from TMDB"""
    try:
        cache_key = "tmdb_genres"
        genres = cache.get(cache_key)
        
        if genres is None:
            url = f"https://api.themoviedb.org/3/genre/movie/list?api_key={TMDB_API_KEY}&language=en-US"
            res = requests.get(url).json()
            genres = {g['id']: g['name'] for g in res['genres']}
            cache.set(cache_key, genres, timeout=86400)  # Cache for 24 hours
        
        return genres
    except Exception as e:
        logger.error(f"Error getting genres: {e}")
        return {}

# ---------- Step 2: Get movie details with genres ----------
def get_movie_with_genres(movie_id):
    """Get movie details including genre IDs"""
    try:
        url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}&language=en-US"
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

# ---------- Step 3: Get popular movies with genres ----------
def get_popular_movies_with_genres(limit=50):
    """Get popular movies with their genre information"""
    try:
        url = f"https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&language=en-US&page=1"
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

# ---------- Step 4: Assign genre vectors ----------
def assign_movie_vectors(movies, all_genre_ids):
    """Assign genre vectors to movies"""
    for movie in movies:
        vector = [1 if gid in movie['genres'] else 0 for gid in all_genre_ids]
        movie['vector'] = vector
    return movies

# ---------- Step 5: Cosine Similarity ----------
def cosine_similarity(movie1, movie2):
    """Calculate cosine similarity between two movies based on their genre vectors"""
    if 'vector' not in movie1 or 'vector' not in movie2:
        return 0
        
    dot_product = sum(a*b for a, b in zip(movie1['vector'], movie2['vector']))
    magnitude1 = sum(a**2 for a in movie1['vector']) ** 0.5
    magnitude2 = sum(b**2 for b in movie2['vector']) ** 0.5
    
    if magnitude1 == 0 or magnitude2 == 0:
        return 0
    
    return dot_product / (magnitude1 * magnitude2)

# ---------- Step 6: Recommend Similar Movies ----------
def recommend_similar_movies(user_selected_movie, movie_list, num_recommendations=8):
    """Recommend similar movies based on cosine similarity"""
    similarities = {}
    
    for movie in movie_list:
        if movie['id'] != user_selected_movie['id']:
            sim = cosine_similarity(user_selected_movie, movie)
            similarities[movie['id']] = sim

    sorted_movies = sorted(similarities.items(), key=lambda x: x[1], reverse=True)
    top_movies = sorted_movies[:num_recommendations]

    recommendations = []
    for movie_id, score in top_movies:
        movie = next((m for m in movie_list if m['id'] == movie_id), None)
        if movie:
            # Convert to the format expected by templates
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

# ---------- Main function for getting similar movies for a specific movie ----------
def get_similar_movies_for_movie(movie_id, num_recommendations=8):
    """Get similar movies for a specific movie using cosine similarity"""
    try:
        # Get genres
        genre_dict = get_genres()
        all_genre_ids = list(genre_dict.keys())
        
        if not all_genre_ids:
            logger.error("Could not fetch genres")
            return []
        
        # Get the target movie
        target_movie = get_movie_with_genres(movie_id)
        if not target_movie:
            logger.error(f"Could not fetch movie {movie_id}")
            return []
        
        # Get popular movies for comparison
        popular_movies = get_popular_movies_with_genres(limit=100)
        if not popular_movies:
            logger.error("Could not fetch popular movies")
            return []
        
        # Add target movie to the list for vector assignment
        all_movies = [target_movie] + popular_movies
        
        # Assign genre vectors
        all_movies = assign_movie_vectors(all_movies, all_genre_ids)
        
        # Get recommendations
        recommendations = recommend_similar_movies(target_movie, all_movies, num_recommendations)
        
        return recommendations
        
    except Exception as e:
        logger.error(f"Error getting similar movies for movie {movie_id}: {e}")
        return []

# ---------- Function for Django view to get cosine similarity recommendations ----------
def get_cosine_similarity_recommendations(user_movie_ids, num_recommendations=20):
    """Get recommendations based on user's movie history using cosine similarity"""
    try:
        if not user_movie_ids:
            return []
        
        # Get genres
        genre_dict = get_genres()
        all_genre_ids = list(genre_dict.keys())
        
        if not all_genre_ids:
            logger.error("Could not fetch genres")
            return []
        
        # Get user's movies with genres
        user_movies = []
        for movie_id in user_movie_ids[:10]:  # Limit to first 10 movies
            movie = get_movie_with_genres(movie_id)
            if movie:
                user_movies.append(movie)
        
        if not user_movies:
            return []
        
        # Get popular movies for comparison
        popular_movies = get_popular_movies_with_genres(limit=200)
        if not popular_movies:
            logger.error("Could not fetch popular movies")
            return []
        
        # Combine all movies and assign vectors
        all_movies = user_movies + popular_movies
        all_movies = assign_movie_vectors(all_movies, all_genre_ids)
        
        # Calculate average similarity for each popular movie
        movie_scores = {}
        user_movie_vectors = [m for m in all_movies if m['id'] in user_movie_ids]
        popular_movie_vectors = [m for m in all_movies if m['id'] not in user_movie_ids]
        
        for popular_movie in popular_movie_vectors:
            total_similarity = 0
            for user_movie in user_movie_vectors:
                similarity = cosine_similarity(user_movie, popular_movie)
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
