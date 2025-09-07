"""
Advanced Recommendation Engine - Centralized recommendation system
"""
import logging
from typing import List, Dict, Optional, Any, Tuple
from django.core.cache import cache
from django.conf import settings
from datetime import datetime
import math

from .movie_service import MovieService
from .user_service import UserService

logger = logging.getLogger(__name__)


class RecommendationEngine:
    """Advanced recommendation engine with multiple algorithms"""
    
    def __init__(self):
        self.movie_service = MovieService()
        self.user_service = UserService()
        self.genre_cache = {}
        self.movie_vectors_cache = {}
    
    def get_personalized_recommendations(self, user_id: int, limit: int = 20, 
                                       algorithm: str = 'hybrid') -> List[Dict[str, Any]]:
        """Get personalized recommendations using specified algorithm"""
        try:
            cache_key = f"personalized_recs_{user_id}_{algorithm}_{limit}"
            recommendations = cache.get(cache_key)
            
            if recommendations is not None:
                logger.info(f"Retrieved {len(recommendations)} recommendations from cache for user {user_id}")
                return recommendations
            
            if algorithm == 'content_based':
                recommendations = self._content_based_recommendations(user_id, limit)
            elif algorithm == 'collaborative':
                recommendations = self._collaborative_filtering_recommendations(user_id, limit)
            elif algorithm == 'hybrid':
                recommendations = self._hybrid_recommendations(user_id, limit)
            else:
                recommendations = self._content_based_recommendations(user_id, limit)
            
            # Cache for 1 hour
            cache.set(cache_key, recommendations, timeout=3600)
            logger.info(f"Generated {len(recommendations)} {algorithm} recommendations for user {user_id}")
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error generating personalized recommendations for user {user_id}: {e}")
            return self._fallback_recommendations(limit)
    
    def _content_based_recommendations(self, user_id: int, limit: int) -> List[Dict[str, Any]]:
        """Content-based recommendations using genre similarity"""
        try:
            # Get user's movie history
            user_movies = self._get_user_movie_history(user_id)
            if not user_movies:
                return self._fallback_recommendations(limit)
            
            # Get genre preferences
            genre_preferences = self._calculate_genre_preferences(user_movies)
            
            # Get candidate movies
            candidate_movies = self.movie_service.get_popular_movies(limit=200)
            
            # Score movies based on genre preferences
            scored_movies = []
            for movie in candidate_movies:
                if movie['id'] in [m['id'] for m in user_movies]:
                    continue  # Skip already watched movies
                
                score = self._calculate_genre_score(movie, genre_preferences)
                if score > 0:
                    movie['recommendation_score'] = score
                    scored_movies.append(movie)
            
            # Sort by score and return top recommendations
            scored_movies.sort(key=lambda x: x['recommendation_score'], reverse=True)
            return scored_movies[:limit]
            
        except Exception as e:
            logger.error(f"Error in content-based recommendations: {e}")
            return self._fallback_recommendations(limit)
    
    def _collaborative_filtering_recommendations(self, user_id: int, limit: int) -> List[Dict[str, Any]]:
        """Collaborative filtering recommendations based on similar users"""
        try:
            from ..mongodb_client import ratings_collection
            
            # Get all ratings
            all_ratings = list(ratings_collection.find({}))
            if not all_ratings:
                return self._fallback_recommendations(limit)
            
            # Build user-item matrix
            user_item_matrix = self._build_user_item_matrix(all_ratings)
            
            # Find similar users
            similar_users = self._find_similar_users(user_id, user_item_matrix)
            if not similar_users:
                return self._fallback_recommendations(limit)
            
            # Get recommendations from similar users
            recommendations = self._get_recommendations_from_similar_users(
                user_id, similar_users, user_item_matrix, limit
            )
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error in collaborative filtering recommendations: {e}")
            return self._fallback_recommendations(limit)
    
    def _hybrid_recommendations(self, user_id: int, limit: int) -> List[Dict[str, Any]]:
        """Hybrid recommendations combining content-based and collaborative filtering"""
        try:
            # Get content-based recommendations
            content_recs = self._content_based_recommendations(user_id, limit * 2)
            
            # Get collaborative filtering recommendations
            collab_recs = self._collaborative_filtering_recommendations(user_id, limit * 2)
            
            # Combine and re-rank
            combined_recs = self._combine_recommendations(content_recs, collab_recs, limit)
            
            return combined_recs
            
        except Exception as e:
            logger.error(f"Error in hybrid recommendations: {e}")
            return self._fallback_recommendations(limit)
    
    def _get_user_movie_history(self, user_id: int) -> List[Dict[str, Any]]:
        """Get user's movie history (viewed + watchlist + rated)"""
        try:
            from ..mongodb_client import viewed_movies_collection, watchlists_collection, ratings_collection
            
            # Get viewed movies
            viewed_movies = list(viewed_movies_collection.find({'user_id': user_id}))
            viewed_ids = [m['movie_id'] for m in viewed_movies]
            
            # Get watchlist movies
            watchlist_movies = list(watchlists_collection.find({'user_id': user_id}))
            watchlist_ids = [m['movie_id'] for m in watchlist_movies]
            
            # Get rated movies
            rated_movies = list(ratings_collection.find({'user_id': user_id}))
            rated_ids = [m['movie_id'] for m in rated_movies]
            
            # Combine all movie IDs
            all_movie_ids = list(set(viewed_ids + watchlist_ids + rated_ids))
            
            # Get movie details
            movies = []
            for movie_id in all_movie_ids:
                movie = self.movie_service.get_movie(movie_id)
                if movie:
                    # Add user interaction data
                    movie['user_rating'] = next((r['rating'] for r in rated_movies if r['movie_id'] == movie_id), None)
                    movie['in_watchlist'] = movie_id in watchlist_ids
                    movie['viewed'] = movie_id in viewed_ids
                    movies.append(movie)
            
            return movies
            
        except Exception as e:
            logger.error(f"Error getting user movie history: {e}")
            return []
    
    def _calculate_genre_preferences(self, user_movies: List[Dict[str, Any]]) -> Dict[str, float]:
        """Calculate user's genre preferences based on their movie history"""
        genre_scores = {}
        total_movies = len(user_movies)
        
        if total_movies == 0:
            return {}
        
        for movie in user_movies:
            genres = movie.get('genres', [])
            rating = movie.get('user_rating', 3.5)  # Default rating if not available
            
            for genre in genres:
                if genre not in genre_scores:
                    genre_scores[genre] = 0
                genre_scores[genre] += rating
        
        # Normalize scores
        for genre in genre_scores:
            genre_scores[genre] = genre_scores[genre] / total_movies
        
        return genre_scores
    
    def _calculate_genre_score(self, movie: Dict[str, Any], genre_preferences: Dict[str, float]) -> float:
        """Calculate how well a movie matches user's genre preferences"""
        movie_genres = movie.get('genres', [])
        if not movie_genres:
            return 0
        
        total_score = 0
        for genre in movie_genres:
            if genre in genre_preferences:
                total_score += genre_preferences[genre]
        
        # Normalize by number of genres
        return total_score / len(movie_genres) if movie_genres else 0
    
    def _build_user_item_matrix(self, ratings: List[Dict[str, Any]]) -> Dict[int, Dict[int, float]]:
        """Build user-item rating matrix"""
        matrix = {}
        for rating in ratings:
            user_id = rating['user_id']
            movie_id = rating['movie_id']
            rating_value = rating['rating']
            
            if user_id not in matrix:
                matrix[user_id] = {}
            matrix[user_id][movie_id] = rating_value
        
        return matrix
    
    def _find_similar_users(self, user_id: int, user_item_matrix: Dict[int, Dict[int, float]], 
                          top_k: int = 10) -> List[Tuple[int, float]]:
        """Find users similar to the given user using cosine similarity"""
        if user_id not in user_item_matrix:
            return []
        
        user_ratings = user_item_matrix[user_id]
        similarities = []
        
        for other_user_id, other_ratings in user_item_matrix.items():
            if other_user_id == user_id:
                continue
            
            # Calculate cosine similarity
            similarity = self._cosine_similarity(user_ratings, other_ratings)
            if similarity > 0:
                similarities.append((other_user_id, similarity))
        
        # Sort by similarity and return top k
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:top_k]
    
    def _cosine_similarity(self, ratings1: Dict[int, float], ratings2: Dict[int, float]) -> float:
        """Calculate cosine similarity between two rating vectors"""
        # Find common items
        common_items = set(ratings1.keys()) & set(ratings2.keys())
        if not common_items:
            return 0
        
        # Calculate dot product and magnitudes
        dot_product = sum(ratings1[item] * ratings2[item] for item in common_items)
        magnitude1 = math.sqrt(sum(ratings1[item] ** 2 for item in common_items))
        magnitude2 = math.sqrt(sum(ratings2[item] ** 2 for item in common_items))
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0
        
        return dot_product / (magnitude1 * magnitude2)
    
    def _get_recommendations_from_similar_users(self, user_id: int, similar_users: List[Tuple[int, float]], 
                                              user_item_matrix: Dict[int, Dict[int, float]], 
                                              limit: int) -> List[Dict[str, Any]]:
        """Get recommendations from similar users"""
        user_ratings = user_item_matrix.get(user_id, {})
        user_movie_ids = set(user_ratings.keys())
        
        # Collect candidate movies with weighted scores
        movie_scores = {}
        for similar_user_id, similarity in similar_users:
            similar_user_ratings = user_item_matrix.get(similar_user_id, {})
            
            for movie_id, rating in similar_user_ratings.items():
                if movie_id not in user_movie_ids:  # Don't recommend already rated movies
                    if movie_id not in movie_scores:
                        movie_scores[movie_id] = []
                    movie_scores[movie_id].append(rating * similarity)
        
        # Calculate average weighted scores
        scored_movies = []
        for movie_id, scores in movie_scores.items():
            avg_score = sum(scores) / len(scores)
            movie = self.movie_service.get_movie(movie_id)
            if movie:
                movie['recommendation_score'] = avg_score
                scored_movies.append(movie)
        
        # Sort by score and return top recommendations
        scored_movies.sort(key=lambda x: x['recommendation_score'], reverse=True)
        return scored_movies[:limit]
    
    def _combine_recommendations(self, content_recs: List[Dict[str, Any]], 
                               collab_recs: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
        """Combine content-based and collaborative filtering recommendations"""
        # Create a dictionary to track movies and their scores
        combined_scores = {}
        
        # Add content-based recommendations with weight 0.6
        for movie in content_recs:
            movie_id = movie['id']
            score = movie.get('recommendation_score', 0) * 0.6
            combined_scores[movie_id] = {
                'movie': movie,
                'score': score,
                'content_score': movie.get('recommendation_score', 0)
            }
        
        # Add collaborative filtering recommendations with weight 0.4
        for movie in collab_recs:
            movie_id = movie['id']
            score = movie.get('recommendation_score', 0) * 0.4
            
            if movie_id in combined_scores:
                combined_scores[movie_id]['score'] += score
                combined_scores[movie_id]['collab_score'] = movie.get('recommendation_score', 0)
            else:
                combined_scores[movie_id] = {
                    'movie': movie,
                    'score': score,
                    'collab_score': movie.get('recommendation_score', 0)
                }
        
        # Sort by combined score and return top recommendations
        sorted_movies = sorted(combined_scores.values(), key=lambda x: x['score'], reverse=True)
        recommendations = []
        
        for item in sorted_movies[:limit]:
            movie = item['movie'].copy()
            movie['recommendation_score'] = item['score']
            movie['content_score'] = item.get('content_score', 0)
            movie['collab_score'] = item.get('collab_score', 0)
            recommendations.append(movie)
        
        return recommendations
    
    def _fallback_recommendations(self, limit: int) -> List[Dict[str, Any]]:
        """Fallback to popular movies if recommendation algorithms fail"""
        try:
            return self.movie_service.get_popular_movies(limit=limit)
        except Exception as e:
            logger.error(f"Error in fallback recommendations: {e}")
            return []
    
    def get_trending_recommendations(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get trending movie recommendations"""
        try:
            cache_key = f"trending_recommendations_{limit}"
            recommendations = cache.get(cache_key)
            
            if recommendations is not None:
                return recommendations
            
            recommendations = self.movie_service.get_trending_movies(limit=limit)
            cache.set(cache_key, recommendations, timeout=3600)  # Cache for 1 hour
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error getting trending recommendations: {e}")
            return self._fallback_recommendations(limit)
    
    def get_similar_movies(self, movie_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get movies similar to a given movie"""
        try:
            cache_key = f"similar_movies_{movie_id}_{limit}"
            similar_movies = cache.get(cache_key)
            
            if similar_movies is not None:
                return similar_movies
            
            # Get the target movie
            target_movie = self.movie_service.get_movie(movie_id)
            if not target_movie:
                return []
            
            # Get candidate movies
            candidate_movies = self.movie_service.get_popular_movies(limit=100)
            
            # Calculate similarity scores
            scored_movies = []
            target_genres = set(target_movie.get('genres', []))
            
            for movie in candidate_movies:
                if movie['id'] == movie_id:
                    continue
                
                movie_genres = set(movie.get('genres', []))
                if not movie_genres:
                    continue
                
                # Calculate Jaccard similarity for genres
                intersection = len(target_genres & movie_genres)
                union = len(target_genres | movie_genres)
                similarity = intersection / union if union > 0 else 0
                
                if similarity > 0:
                    movie['similarity_score'] = similarity
                    scored_movies.append(movie)
            
            # Sort by similarity and return top recommendations
            scored_movies.sort(key=lambda x: x['similarity_score'], reverse=True)
            similar_movies = scored_movies[:limit]
            
            cache.set(cache_key, similar_movies, timeout=3600)  # Cache for 1 hour
            return similar_movies
            
        except Exception as e:
            logger.error(f"Error getting similar movies for {movie_id}: {e}")
            return []
