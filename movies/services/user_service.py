"""
User Service - Handles all user-related business logic
"""
import logging
from typing import List, Dict, Optional, Any
from django.core.cache import cache
from django.utils import timezone
from datetime import datetime

from ..repositories.watchlist_repository import WatchlistRepository
from ..repositories.ratings_repository import RatingsRepository
from ..repositories.viewed_movies_repository import ViewedMoviesRepository
from ..repositories.search_history_repository import SearchHistoryRepository

logger = logging.getLogger(__name__)


class UserService:
    """Service class for handling user-related operations"""
    
    def __init__(self,
                 watchlist_repo: WatchlistRepository | None = None,
                 ratings_repo: RatingsRepository | None = None,
                 viewed_repo: ViewedMoviesRepository | None = None,
                 search_repo: SearchHistoryRepository | None = None):
        self.watchlist_repo = watchlist_repo or WatchlistRepository()
        self.ratings_repo = ratings_repo or RatingsRepository()
        self.viewed_repo = viewed_repo or ViewedMoviesRepository()
        self.search_repo = search_repo or SearchHistoryRepository()
    
    def get_user_watchlist(self, user_id: int) -> List[Dict[str, Any]]:
        """Get watchlist for a user from cache or MongoDB"""
        try:
            # Try to get from cache first
            cache_key = f"user_watchlist_{user_id}"
            watchlist = cache.get(cache_key)
            
            if watchlist is None:
                logger.info(f"Cache miss for user {user_id} watchlist")
                # Not in cache, get from repository
                watchlist = self.watchlist_repo.find_by_user(user_id)
                
                logger.info(f"Retrieved {len(watchlist)} items from MongoDB for user {user_id}")
                
                # Store in cache for future requests (cache for 30 minutes)
                cache.set(cache_key, watchlist, timeout=1800)
            else:
                logger.info(f"Cache hit for user {user_id} watchlist")
            
            return watchlist
        except Exception as e:
            logger.error(f"Error getting user watchlist: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def add_to_watchlist(self, user_id: int, movie_id: int) -> bool:
        """Add a movie to user's watchlist"""
        try:
            # Ensure movie_id is an integer
            movie_id = int(movie_id)
            
            self.watchlist_repo.upsert(user_id, movie_id, timezone.now())
            
            # Invalidate cache for this user's watchlist
            self._invalidate_watchlist_cache(user_id)
            logger.info(f"Added movie {movie_id} to watchlist for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error adding to watchlist: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def remove_from_watchlist(self, user_id: int, movie_id: int) -> bool:
        """Remove a movie from user's watchlist"""
        try:
            # Ensure movie_id is an integer
            movie_id = int(movie_id)
            
            deleted = self.watchlist_repo.delete(user_id, movie_id)
            
            # Invalidate cache
            self._invalidate_watchlist_cache(user_id)
            
            logger.info(f"Removed movie {movie_id} from watchlist for user {user_id}")
            return deleted > 0
        except Exception as e:
            logger.error(f"Error removing from watchlist: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def _invalidate_watchlist_cache(self, user_id: int):
        """Invalidate the cache for a user's watchlist"""
        try:
            cache_key = f"user_watchlist_{user_id}"
            cache.delete(cache_key)
            logger.info(f"Invalidated cache for user {user_id}")
        except Exception as e:
            logger.error(f"Error invalidating cache: {e}")
    
    def get_user_ratings(self, user_id: int) -> List[Dict[str, Any]]:
        """Get user's ratings"""
        try:
            return self.ratings_repo.find_by_user(user_id)
        except Exception as e:
            logger.error(f"Error getting user ratings: {e}")
            return []
    
    def save_user_rating(self, user_id: int, movie_id: int, rating: int) -> bool:
        """Save or update a user's rating for a movie"""
        try:
            if rating < 1 or rating > 5:
                return False
            
            self.ratings_repo.upsert(user_id, movie_id, rating)
            
            # Invalidate any caches if needed
            self._invalidate_rating_cache(user_id)
            return True
        except Exception as e:
            logger.error(f"Error saving rating: {e}")
            return False
    
    def _invalidate_rating_cache(self, user_id: int):
        """Invalidate rating-related caches"""
        try:
            cache.delete(f"user_ratings_{user_id}")
            cache.delete(f"user_recommendations_{user_id}")
        except Exception as e:
            logger.error(f"Error invalidating rating cache: {e}")

    def delete_user_rating(self, user_id: int, movie_id: int) -> bool:
        """Delete a single rating for the user and invalidate caches."""
        try:
            deleted = self.ratings_repo.delete_one(user_id, movie_id)
            if deleted:
                self._invalidate_rating_cache(user_id)
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting rating for user {user_id} movie {movie_id}: {e}")
            return False

    # Reviews
    def save_review(self, user_id: int, movie_id: int, text: str) -> bool:
        try:
            self.ratings_repo.upsert_review(user_id, movie_id, text, datetime.now())
            return True
        except Exception as e:
            logger.error(f"Error saving review for user {user_id} movie {movie_id}: {e}")
            return False

    def delete_review(self, user_id: int, movie_id: int) -> bool:
        try:
            return self.ratings_repo.delete_review(user_id, movie_id) > 0
        except Exception as e:
            logger.error(f"Error deleting review for user {user_id} movie {movie_id}: {e}")
            return False

    def list_reviews(self, movie_id: int, limit: int = 50):
        try:
            return self.ratings_repo.list_reviews_for_movie(movie_id, limit)
        except Exception as e:
            logger.error(f"Error listing reviews for movie {movie_id}: {e}")
            return []

    def delete_account(self, user) -> bool:
        """Delete a user's profile and related data across repositories, then delete Django user."""
        try:
            user_id = user.id
            # Delete domain data
            self.watchlist_repo.delete_by_user(user_id)
            self.viewed_repo.delete_by_user(user_id)
            self.ratings_repo.delete_by_user(user_id)
            self.search_repo.delete_by_user(user_id)

            # Invalidate caches
            try:
                cache.delete(f"user_watchlist_{user_id}")
                cache.delete(f"user_watchlist_details_{user_id}")
                cache.delete(f"user_recommendations_{user_id}")
            except Exception:
                pass

            # Delete the Django auth user WITHOUT triggering ORM cascades
            # (to avoid touching unmanaged proxy tables like movies_watchlist)
            try:
                from django.contrib.auth import get_user_model
                from django.db import connection
                UserModel = get_user_model()
                user_table = UserModel._meta.db_table
                with connection.cursor() as cursor:
                    cursor.execute(f"DELETE FROM {user_table} WHERE id = %s", [user_id])
            except Exception as e:
                logger.error(f"Error deleting Django user {user_id}: {e}")
                return False

            return True
        except Exception as e:
            logger.error(f"Error deleting account for user {getattr(user, 'id', 'unknown')}: {e}")
            return False
    
    def get_user_viewed_movies(self, user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        """Get user's viewed movies"""
        try:
            return self.viewed_repo.find_recent_by_user(user_id, limit)
        except Exception as e:
            logger.error(f"Error getting user viewed movies: {e}")
            return []
    
    def record_movie_view(self, user_id: int, movie_id: int) -> bool:
        """Record that a user viewed a movie"""
        try:
            self.viewed_repo.upsert(user_id, movie_id)
            return True
        except Exception as e:
            logger.error(f"Error recording movie view: {e}")
            return False
    
    def get_user_search_history(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get user's search history"""
        try:
            return self.search_repo.find_recent_by_user(user_id, limit)
        except Exception as e:
            logger.error(f"Error getting user search history: {e}")
            return []
    
    def save_search_query(self, user_id: int, query: str, filters: Optional[Dict] = None) -> bool:
        """Save a search query to user's history"""
        try:
            self.search_repo.insert(user_id, query, filters or {})
            return True
        except Exception as e:
            logger.error(f"Error saving search query: {e}")
            return False
    
    def get_user_statistics(self, user_id: int) -> Dict[str, int]:
        """Get user's movie statistics"""
        try:
            viewed_count = len(self.viewed_repo.find_recent_by_user(user_id, limit=10**9))
            watchlist_count = len(self.watchlist_repo.find_by_user(user_id))
            ratings_count = len(self.ratings_repo.find_by_user(user_id))
            
            return {
                'viewed_count': viewed_count,
                'watchlist_count': watchlist_count,
                'ratings_count': ratings_count
            }
        except Exception as e:
            logger.error(f"Error getting user statistics: {e}")
            return {
                'viewed_count': 0,
                'watchlist_count': 0,
                'ratings_count': 0
            }
