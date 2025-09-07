"""
Repository for watchlists collection
"""
import logging
from datetime import datetime
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class WatchlistRepository:
    """Data access for watchlists in MongoDB."""

    def __init__(self):
        from ..mongodb_client import watchlists_collection
        self.collection = watchlists_collection

    def find_by_user(self, user_id: int) -> List[Dict]:
        try:
            return list(self.collection.find({'user_id': user_id}).sort('added_at', -1))
        except Exception as e:
            logger.error(f"WatchlistRepository.find_by_user error: {e}")
            return []

    def upsert(self, user_id: int, movie_id: int, added_at: Optional[datetime] = None) -> None:
        try:
            self.collection.update_one(
                {'user_id': user_id, 'movie_id': int(movie_id)},
                {'$set': {
                    'user_id': user_id,
                    'movie_id': int(movie_id),
                    'added_at': added_at or datetime.now()
                }},
                upsert=True
            )
        except Exception as e:
            logger.error(f"WatchlistRepository.upsert error: {e}")

    def delete(self, user_id: int, movie_id: int) -> int:
        try:
            result = self.collection.delete_one({'user_id': user_id, 'movie_id': int(movie_id)})
            return getattr(result, 'deleted_count', 0)
        except Exception as e:
            logger.error(f"WatchlistRepository.delete error: {e}")
            return 0

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
            logger.error(f"WatchlistRepository.delete_by_user error: {e}")
            return 0


