import logging
from typing import List, Dict, Any, Optional


logger = logging.getLogger(__name__)


class TMDBClient:
    """Service wrapper for TMDB API operations.

    For now, this delegates to existing module-level functions in `movies.movie_data`.
    This provides a clean OOP interface that can be evolved without changing callers.
    """

    @staticmethod
    def get_movie(movie_id: int) -> Optional[Dict[str, Any]]:
        from movies.movie_data import get_movie as _get_movie
        return _get_movie(movie_id)

    @staticmethod
    def get_popular_movies(page: int = 1, limit: int = 20) -> List[Dict[str, Any]]:
        from movies.movie_data import get_popular_movies as _get_popular_movies
        return _get_popular_movies(page=page, limit=limit)

    @staticmethod
    def get_trending_movies(time_window: str = 'week', page: int = 1) -> List[Dict[str, Any]]:
        from movies.movie_data import get_trending_movies as _get_trending_movies
        return _get_trending_movies(time_window=time_window, page=page)

    @staticmethod
    def search_movies(query: str, page: int = 1) -> List[Dict[str, Any]]:
        from movies.movie_data import search_movies as _search_movies
        return _search_movies(query, page=page)

    @staticmethod
    def get_actor_details(actor_id: int) -> Optional[Dict[str, Any]]:
        from movies.movie_data import get_actor_details as _get_actor_details
        return _get_actor_details(actor_id)

    @staticmethod
    def get_actor_movies(actor_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        from movies.movie_data import get_actor_movies as _get_actor_movies
        return _get_actor_movies(actor_id, limit=limit)

    @staticmethod
    def get_recommendations_for_movies(movie_ids: List[int], limit: int = 20) -> List[Dict[str, Any]]:
        from movies.movie_data import get_recommendations_for_movies as _get_recs
        return _get_recs(movie_ids, limit=limit)

    @staticmethod
    def search_movies_by_filters(
        query: Optional[str] = None,
        year: Optional[str] = None,
        genre: Optional[str] = None,
        language: Optional[str] = None,
        page: int = 1,
    ) -> List[Dict[str, Any]]:
        from movies.movie_data import search_movies_by_filters as _search_movies_by_filters
        return _search_movies_by_filters(query=query, year=year, genre=genre, language=language, page=page)

    @staticmethod
    def get_movie_genres(movie_id: int) -> List[str]:
        from movies.movie_data import get_movie_genres as _get_movie_genres
        return _get_movie_genres(movie_id)

    @staticmethod
    def search_movies_by_person(person_id: int) -> List[Dict[str, Any]]:
        from movies.movie_data import search_movies_by_person as _search_movies_by_person
        return _search_movies_by_person(person_id)

