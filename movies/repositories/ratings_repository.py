"""
Repository for ratings collection
"""
import logging
from datetime import datetime
from typing import List, Dict

logger = logging.getLogger(__name__)


class RatingsRepository:
    """Data access for ratings in MongoDB."""

    def __init__(self):
        from ..mongodb_client import ratings_collection
        self.collection = ratings_collection

    def find_by_user(self, user_id: int) -> List[Dict]:
        try:
            return list(self.collection.find({'user_id': user_id}).sort('updated_at', -1))
        except Exception as e:
            logger.error(f"RatingsRepository.find_by_user error: {e}")
            return []

    def upsert(self, user_id: int, movie_id: int, rating: int) -> None:
        try:
            self.collection.update_one(
                {'user_id': user_id, 'movie_id': int(movie_id)},
                {'$set': {
                    'user_id': user_id,
                    'movie_id': int(movie_id),
                    'rating': int(rating),
                    'updated_at': datetime.now()
                }},
                upsert=True
            )
        except Exception as e:
            logger.error(f"RatingsRepository.upsert error: {e}")

    def count_by_movie(self, movie_id: int) -> int:
        try:
            return int(self.collection.count_documents({'movie_id': int(movie_id)}))
        except Exception:
            return 0

    def iter_by_movie(self, movie_id: int):
        try:
            return self.collection.find({'movie_id': int(movie_id)})
        except Exception:
            return []

    def delete_by_user(self, user_id: int) -> int:
        try:
            result = self.collection.delete_many({'user_id': user_id})
            return getattr(result, 'deleted_count', 0)
        except Exception as e:
            logger.error(f"RatingsRepository.delete_by_user error: {e}")
            return 0

    def delete_one(self, user_id: int, movie_id: int) -> int:
        try:
            result = self.collection.delete_one({'user_id': user_id, 'movie_id': int(movie_id)})
            return getattr(result, 'deleted_count', 0)
        except Exception as e:
            logger.error(f"RatingsRepository.delete_one error: {e}")
            return 0


