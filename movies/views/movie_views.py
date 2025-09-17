"""
Movie-related views using class-based approach
"""
import logging
from django.shortcuts import render, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views.generic import View, TemplateView
from django.http import JsonResponse
from django.core.cache import cache
from datetime import datetime

from ..services.movie_service import MovieService
from ..services.user_service import UserService
from ..services.recommendation_engine import RecommendationEngine
 

logger = logging.getLogger(__name__)


class HomeView(TemplateView):
    """Home page view showing personalized or popular movies"""
    template_name = 'home.html'
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.movie_service = MovieService()
        self.user_service = UserService()
        self.recommendation_engine = RecommendationEngine()
        
    def get(self, request, *args, **kwargs):
        # Redirect only true new users (no prefs, no ratings, no watchlist, no views)
        try:
            if request.user.is_authenticated:
                if self.recommendation_engine.is_new_user(request.user.id):
                    return redirect('preferences')
        except Exception:
            pass
        return super().get(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        try:
            # Fetch trending movies (top 10)
            try:
                trending_movies = self.movie_service.get_trending_movies(time_window='week', page=1)[:10]
            except Exception:
                trending_movies = []
            # Fallback: if TMDB trending is empty/unavailable, use popular
            if not trending_movies:
                try:
                    trending_movies = self.movie_service.get_popular_movies(limit=10)
                except Exception:
                    trending_movies = []

            if self.request.user.is_authenticated:
                # Personalized Featured For You using preferences-based engine
                try:
                    featured_for_you = self.recommendation_engine.get_featured_for_you(self.request.user.id, limit=12)
                except Exception:
                    featured_for_you = []
                # Item-based CF
                try:
                    item_based = self.recommendation_engine.get_item_based_recommendations(self.request.user.id, limit=12)
                except Exception:
                    item_based = []
                # User-based CF
                try:
                    user_based = self.recommendation_engine.get_user_based_recommendations(self.request.user.id, limit=12)
                except Exception:
                    user_based = []
            else:
                featured_for_you = []
                item_based = []
                user_based = []

            # Featured movies (base grid)
            movies = self.movie_service.get_popular_movies(limit=20)
            
            featured_movies = movies

            context.update({
                'movies': featured_movies,
                'trending_movies': trending_movies,
                'featured_for_you': featured_for_you,
                'item_based_recs': item_based,
                'user_based_recs': user_based,
                'page_title': 'Featured Movies'
            })
            
        except Exception as e:
            logger.error(f"Error in home view: {e}")
            messages.error(self.request, "An error occurred while loading the home page. Please try again later.")
            # Fallback
            movies = self.movie_service.get_popular_movies(limit=20)
            try:
                trending_movies = self.movie_service.get_trending_movies(time_window='week', page=1)[:10]
            except Exception:
                trending_movies = []
            featured_movies = movies
            
            context.update({
                'movies': featured_movies,
                'trending_movies': trending_movies,
                'featured_for_you': [],
                'page_title': 'Featured Movies'
            })
        
        return context
    

class MovieDetailView(TemplateView):
    """Show details for a specific movie"""
    template_name = 'movie_detail.html'
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.movie_service = MovieService()
        self.user_service = UserService()
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        movie_id = kwargs.get('movie_id')
        
        try:
            from datetime import datetime
            
            # Get current date for filtering unreleased movies
            current_date = datetime.now().strftime('%Y-%m-%d')
            
            # Get movie details
            movie = self.movie_service.get_movie(movie_id)
            if not movie:
                messages.warning(self.request, "Movie not found.")
                return redirect('home')
            
            # Get movies featuring the first cast member (if available)
            first_cast_movies = []
            if movie.get('first_cast'):
                first_cast_id = movie['first_cast']['id']
                first_cast_movies = self.movie_service.get_actor_movies(first_cast_id)
                # Remove the current movie from the list
                first_cast_movies = [m for m in first_cast_movies if m['id'] != movie_id]
                
                # Filter out unreleased movies
                first_cast_movies = [m for m in first_cast_movies if m.get('release_date') and m['release_date'] <= current_date]
                
                # Sort by release date (newest first)
                first_cast_movies.sort(key=lambda x: x.get('release_date', ''), reverse=True)
                
                # Limit to 20 movies
                first_cast_movies = first_cast_movies[:20]
            
            # Record this movie as viewed by the user (if logged in)
            if self.request.user.is_authenticated:
                self.user_service.record_movie_view(self.request.user.id, movie_id)
            
            # Get user's existing rating for this movie
            user_rating = None
            if self.request.user.is_authenticated:
                try:
                    from ..mongodb_client import ratings_collection
                    rating_doc = ratings_collection.find_one({'user_id': self.request.user.id, 'movie_id': int(movie_id)})
                    if rating_doc:
                        user_rating = rating_doc.get('rating')
                except Exception:
                    user_rating = None

            # Reviews for this movie
            try:
                from ..repositories.ratings_repository import RatingsRepository
                reviews = RatingsRepository().list_reviews_for_movie(int(movie_id), limit=50)
            except Exception:
                reviews = []

            context.update({
                'movie': movie,
                'first_cast_movies': first_cast_movies,
                'user_rating': user_rating,
                'reviews': reviews
            })
            
        except Exception as e:
            logger.error(f"Error in movie_detail view for movie {movie_id}: {e}")
            messages.error(self.request, "An error occurred while loading movie details. Please try again later.")
            return redirect('home')
        
        return context


class MovieSearchView(TemplateView):
    """Search and filter movies"""
    template_name = 'movie_search.html'
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.movie_service = MovieService()
        self.user_service = UserService()


class MovieFilterAjaxView(View):
    """AJAX endpoint for filtering movies"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.movie_service = MovieService()
        self.user_service = UserService()
    
    def get(self, request):
        try:
            import re
            from datetime import datetime
            
            # Get filter parameters
            query = request.GET.get('query', '').strip()
            genre = request.GET.get('genre', '').strip()
            year = request.GET.get('year', '').strip()
            language = request.GET.get('language', '').strip()
            
            # Log the search if user is authenticated
            if request.user.is_authenticated and (query or genre or year or language):
                try:
                    self.user_service.save_search_query(
                        request.user.id, 
                        query, 
                        {'genre': genre, 'year': year, 'language': language}
                    )
                    logger.info(f"Logged filtered search for user {request.user.id}")
                except Exception as e:
                    logger.error(f"Error logging search: {e}")
            
            # Different search strategies based on provided filters
            results = []
            
            # Case 1: Title search (with or without other filters)
            if query:
                results = self.movie_service.search_movies(query)
                
                # Apply additional filters if provided
                if year:
                    year_pattern = re.compile(f'^{year}')
                    results = [movie for movie in results if movie.get('release_date') and year_pattern.match(movie.get('release_date', ''))]
                
                if genre:
                    results = [movie for movie in results if genre.lower() in [g.lower() for g in movie.get('genres', [])]]
                
                if language:
                    results = [movie for movie in results if movie.get('original_language') == language]
            
            # Case 2: No title, but other filters
            else:
                # Start with popular movies as base
                results = self.movie_service.get_popular_movies(limit=100)
                
                # Apply filters
                if year:
                    year_pattern = re.compile(f'^{year}')
                    results = [movie for movie in results if movie.get('release_date') and year_pattern.match(movie.get('release_date', ''))]
                
                if genre:
                    results = [movie for movie in results if genre.lower() in [g.lower() for g in movie.get('genres', [])]]
                
                if language:
                    results = [movie for movie in results if movie.get('original_language') == language]
                
                # If only year is provided, prioritize Tamil and English movies
                if year and not genre and not language:
                    tamil_english = [movie for movie in results if movie.get('original_language') in ['ta', 'en']]
                    other_langs = [movie for movie in results if movie.get('original_language') not in ['ta', 'en']]
                    
                    tamil_english.sort(key=lambda x: x.get('vote_average', 0), reverse=True)
                    other_langs.sort(key=lambda x: x.get('vote_average', 0), reverse=True)
                    
                    results = tamil_english + other_langs
                
                # If only genre is provided, sort by release date (newest first)
                if genre and not year and not language:
                    results.sort(key=lambda x: x.get('release_date', ''), reverse=True)
            
            # Limit results to 50 for performance
            results = results[:50]
            
            return JsonResponse({
                'movies': results,
                'count': len(results)
            })
            
        except Exception as e:
            logger.error(f"Error in movie filter: {e}")
            return JsonResponse({
                'movies': [],
                'count': 0,
                'error': str(e)
            })


class ActorMoviesView(TemplateView):
    """Show movies for a specific actor"""
    template_name = 'actor_movies.html'
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.movie_service = MovieService()
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        actor_id = kwargs.get('actor_id')
        
        try:
            # Get actor details
            actor = self.movie_service.get_actor_details(actor_id)
            if not actor:
                messages.warning(self.request, "Actor not found.")
                return redirect('home')
            
            # Get movies for this actor
            movies = self.movie_service.get_actor_movies(actor_id)
            
            context.update({
                'actor': actor,
                'movies': movies
            })
            
        except Exception as e:
            logger.error(f"Error in actor_movies view for actor {actor_id}: {e}")
            messages.error(self.request, "An error occurred while loading actor information. Please try again later.")
            return redirect('home')
        
        return context


class SearchView(TemplateView):
    """Movie search view using MovieService with optional filters"""
    template_name = 'search.html'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.movie_service = MovieService()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        query = self.request.GET.get('q', '').strip()
        year = self.request.GET.get('year', '').strip()
        genre = self.request.GET.get('genre', '').strip()
        language = self.request.GET.get('language', '').strip()

        from datetime import datetime as dt
        current_year = dt.now().year
        year_range = list(range(current_year, 1950, -1))

        results = []
        try:
            if query:
                results = self.movie_service.search_movies(query)

                # Optional filters
                if year:
                    results = [m for m in results if (m.get('release_date') or '').startswith(year)]
                if genre:
                    results = [m for m in results if genre.lower() in [g.lower() for g in m.get('genres', [])]]
                if language:
                    results = [m for m in results if m.get('original_language') == language]
            else:
                # No query: start from popular and filter if filters were provided
                if year or genre or language:
                    base = self.movie_service.get_popular_movies(limit=100)
                    # genres may be missing on popular; keep basic filters
                    if year:
                        base = [m for m in base if (m.get('release_date') or '').startswith(year)]
                    if language:
                        base = [m for m in base if m.get('original_language') == language]
                    # genre filter best-effort; many items won't include genres here
                    if genre:
                        base = [m for m in base if genre.lower() in [g.lower() for g in m.get('genres', [])]]
                    results = base
        except Exception:
            results = []

        context.update({
            'results': results,
            'query': query,
            'year': year,
            'genre': genre,
            'language': language,
            'year_range': year_range,
        })

        return context
