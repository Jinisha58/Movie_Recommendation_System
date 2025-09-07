"""
Repository for search_history collection
"""
import logging
from datetime import datetime
from typing import List, Dict

logger = logging.getLogger(__name__)


class SearchHistoryRepository:
    """Data access for search_history in MongoDB."""

    def __init__(self):
        from ..mongodb_client import search_history_collection
        self.collection = search_history_collection

    def find_recent_by_user(self, user_id: int, limit: int = 10) -> List[Dict]:
        try:
            return list(self.collection.find({'user_id': user_id}).sort('timestamp', -1).limit(limit))
        except Exception as e:
            logger.error(f"SearchHistoryRepository.find_recent_by_user error: {e}")
            return []

    def insert(self, user_id: int, query: str, filters: Dict) -> None:
        try:
            self.collection.insert_one({
                'user_id': user_id,
                'query': query,
                'filters': filters or {},
                'timestamp': datetime.now()
            })
        except Exception as e:
            logger.error(f"SearchHistoryRepository.insert error: {e}")

    def delete_by_user(self, user_id: int) -> int:
        try:
            result = self.collection.delete_many({'user_id': user_id})
            return getattr(result, 'deleted_count', 0)
        except Exception as e:
            logger.error(f"SearchHistoryRepository.delete_by_user error: {e}")
            return 0


