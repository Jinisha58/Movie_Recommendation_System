"""
Repository for viewed_movies collection
"""
import logging
from datetime import datetime
from typing import List, Dict

logger = logging.getLogger(__name__)


class ViewedMoviesRepository:
    """Data access for viewed_movies in MongoDB."""

    def __init__(self):
        from ..mongodb_client import viewed_movies_collection
        self.collection = viewed_movies_collection

    def find_recent_by_user(self, user_id: int, limit: int = 20) -> List[Dict]:
        try:
            return list(self.collection.find({'user_id': user_id}).sort('last_viewed', -1).limit(limit))
        except Exception as e:
            logger.error(f"ViewedMoviesRepository.find_recent_by_user error: {e}")
            return []

    def upsert(self, user_id: int, movie_id: int) -> None:
        try:
            self.collection.update_one(
                {'user_id': user_id, 'movie_id': int(movie_id)},
                {'$set': {
                    'user_id': user_id,
                    'movie_id': int(movie_id),
                    'last_viewed': datetime.now()
                }},
                upsert=True
            )
        except Exception as e:
            logger.error(f"ViewedMoviesRepository.upsert error: {e}")

    def count_by_movie(self, movie_id: int) -> int:
        try:
            return int(self.collection.count_documents({'movie_id': int(movie_id)}))
        except Exception:
            return 0

    def delete_by_user(self, user_id: int) -> int:
        try:
            result = self.collection.delete_many({'user_id': user_id})
            return getattr(result, 'deleted_count', 0)
        except Exception as e:
            logger.error(f"ViewedMoviesRepository.delete_by_user error: {e}")
            return 0


