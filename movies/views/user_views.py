"""
User-related views using class-based approach
"""
import logging
from django.shortcuts import render, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views.generic import View, TemplateView
from django.http import JsonResponse
from django.core.cache import cache
from django.contrib.auth.forms import UserCreationForm
from datetime import datetime

from ..services.movie_service import MovieService
from ..services.user_service import UserService
 

logger = logging.getLogger(__name__)


class WatchlistView(LoginRequiredMixin, TemplateView):
    """View user's watchlist with robust error handling and fallbacks"""
    template_name = 'watchlist.html'
    login_url = '/login/'
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.movie_service = MovieService()
        self.user_service = UserService()
        from ..services.recommendation_engine import RecommendationEngine
        self.recommendation_engine = RecommendationEngine()
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        try:
            import traceback
            
            # Get user's watchlist (this will use cache if available)
            try:
                watchlist_entries = self.user_service.get_user_watchlist(self.request.user.id)
                logger.info(f"Retrieved {len(watchlist_entries)} watchlist entries for user {self.request.user.id}")
            except Exception as e:
                logger.error(f"Error getting watchlist entries: {e}")
                logger.error(traceback.format_exc())
                watchlist_entries = []
            
            # Create a cache key for the full watchlist with movie details
            cache_key = f"user_watchlist_details_{self.request.user.id}"
            movies = cache.get(cache_key)
            
            if movies is None:
                # Cache miss - need to fetch movie details
                movies = []
                api_errors = 0
                
                for entry in watchlist_entries:
                    try:
                        movie_id = entry.get('movie_id')
                        if not movie_id:
                            logger.warning(f"Missing movie_id in watchlist entry: {entry}")
                            continue
                            
                        movie = self.movie_service.get_movie(movie_id)
                        if movie:
                            # Add the date the movie was added to watchlist
                            movie['added_date'] = entry.get('added_at')
                            movies.append(movie)
                        else:
                            logger.warning(f"Movie with ID {movie_id} not found")
                    except Exception as movie_error:
                        logger.error(f"Error processing movie {entry.get('movie_id', 'unknown')}: {movie_error}")
                        api_errors += 1
                        
                        # If we've had too many API errors, stop trying to fetch more movies
                        if api_errors >= 3:
                            logger.error("Too many API errors, stopping movie fetching")
                            break
                        
                        continue
                
                # Only cache if we have movies and didn't encounter too many errors
                if movies and api_errors < 3:
                    try:
                        cache.set(cache_key, movies, timeout=900)
                    except Exception as cache_error:
                        logger.error(f"Error setting cache: {cache_error}")
            
            logger.info(f"User {self.request.user.id} has {len(movies)} movies in watchlist")

            # Build recommendations based on watchlist genres using cosine similarity
            try:
                recommended_movies = self.recommendation_engine.get_watchlist_based_recommendations(self.request.user.id, limit=12)
            except Exception as rec_err:
                logger.error(f"Error computing watchlist-based recommendations: {rec_err}")
                recommended_movies = []
            
            # Filter out zero-similarity recommendations
            try:
                recommended_movies = [m for m in recommended_movies if float(m.get('similarity_score', 0.0)) > 0.0]
            except Exception:
                recommended_movies = []
            
            # Show recommendations section if we have few items or we have any recs
            has_few = len(movies) < 6 or bool(recommended_movies)
            
            # If we couldn't fetch any movies due to API errors, show a specific message
            if not movies and watchlist_entries:
                messages.warning(self.request, "We're having trouble connecting to our movie database. Your watchlist is still saved, but we can't display the movies right now. Please try again later.")
            
            context.update({
                'movies': movies,
                'recommended_movies': recommended_movies,
                'has_few_movies': has_few
            })
            
        except Exception as e:
            logger.error(f"Error in watchlist view for user {self.request.user.id}: {e}")
            logger.error(traceback.format_exc())
            messages.error(self.request, "An error occurred while loading your watchlist. Please try again later.")
            context.update({'movies': []})
        
        return context


class AddToWatchlistView(LoginRequiredMixin, View):
    """Add a movie to user's watchlist with cache invalidation"""
    login_url = '/login/'
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.movie_service = MovieService()
        self.user_service = UserService()
    
    def post(self, request, movie_id):
        try:
            from django.core.cache import cache
            
            # Convert movie_id to integer to ensure consistency
            movie_id = int(movie_id)
            
            # Check if movie exists
            movie = self.movie_service.get_movie(movie_id)
            if not movie:
                messages.warning(request, "Movie not found.")
                return redirect('home')
            
            # Add to watchlist using our service
            success = self.user_service.add_to_watchlist(request.user.id, movie_id)
            
            if not success:
                messages.error(request, "An error occurred. Please try again later.")
                return redirect('home')
            
            # Also invalidate the full watchlist details cache
            cache.delete(f"user_watchlist_details_{request.user.id}")
            cache.delete(f"user_recommendations_{request.user.id}")
            
            # Check if this is an AJAX request
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.content_type == 'application/json':
                return JsonResponse({'success': True, 'message': 'Movie added to watchlist'})
            
            messages.success(request, f"'{movie['title']}' added to your watchlist.")
            
            # Redirect back to the referring page if available
            referer = request.META.get('HTTP_REFERER')
            if referer:
                return redirect(referer)
            return redirect('movie_detail', movie_id=movie_id)
            
        except Exception as e:
            logger.error(f"Error adding movie {movie_id} to watchlist for user {request.user.id}: {e}")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.content_type == 'application/json':
                return JsonResponse({'success': False, 'message': 'Error adding movie to watchlist'})
            messages.error(request, "An error occurred. Please try again later.")
            return redirect('home')


class RemoveFromWatchlistView(LoginRequiredMixin, View):
    """Remove a movie from user's watchlist with cache invalidation"""
    login_url = '/login/'
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.user_service = UserService()
    
    def post(self, request, movie_id):
        try:
            from django.core.cache import cache
            
            # Convert movie_id to integer to ensure consistency
            movie_id = int(movie_id)
            
            # Remove from watchlist using our service
            success = self.user_service.remove_from_watchlist(request.user.id, movie_id)
            
            # Also invalidate the full watchlist details cache
            cache.delete(f"user_watchlist_details_{request.user.id}")
            cache.delete(f"user_recommendations_{request.user.id}")
            
            # Check if this is an AJAX request
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.content_type == 'application/json':
                if success:
                    return JsonResponse({'success': True, 'message': 'Movie removed from watchlist'})
                else:
                    return JsonResponse({'success': False, 'message': 'Movie was not in watchlist'})
            
            if success:
                messages.success(request, "Movie removed from your watchlist.")
            else:
                messages.info(request, "Movie was not in your watchlist.")
            
            # Redirect back to the watchlist page
            return redirect('watchlist')
            
        except Exception as e:
            logger.error(f"Error removing movie {movie_id} from watchlist for user {request.user.id}: {e}")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.content_type == 'application/json':
                return JsonResponse({'success': False, 'message': 'Error removing movie from watchlist'})
            messages.error(request, "An error occurred. Please try again later.")
            return redirect('watchlist')


 

class ProfileView(LoginRequiredMixin, TemplateView):
    """User profile view"""
    template_name = 'profile.html'
    login_url = '/login/'
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.movie_service = MovieService()
        self.user_service = UserService()
        
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        try:
            # Get user's movie statistics
            stats = self.user_service.get_user_statistics(self.request.user.id)
            
            # Get user ratings
            user_ratings = self.user_service.get_user_ratings(self.request.user.id)
            rated_movies = []
            for r in user_ratings:
                m = self.movie_service.get_movie(r['movie_id'])
                if m:
                    m['user_rating'] = r.get('rating')
                    rated_movies.append(m)
            
            # Get recently viewed movies
            recent_views = self.user_service.get_user_viewed_movies(self.request.user.id, limit=5)
            recent_movies = []
            for view in recent_views:
                movie = self.movie_service.get_movie(view['movie_id'])
                if movie:
                    movie['last_viewed'] = view.get('last_viewed')
                    recent_movies.append(movie)
            
            context.update({
                'user': self.request.user,
                'viewed_count': stats['viewed_count'],
                'watchlist_count': stats['watchlist_count'],
                'ratings_count': stats['ratings_count'],
                'recent_movies': recent_movies,
                'rated_movies': rated_movies
            })
            
        except Exception as e:
            logger.error(f"Error in profile view for user {self.request.user.id}: {e}")
            messages.error(self.request, "An error occurred while loading your profile. Please try again later.")
            context.update({'user': self.request.user})
        
        return context


class MyRatingsView(LoginRequiredMixin, TemplateView):
    """Show only the user's rated movies with their ratings and details."""
    template_name = 'ratings.html'
    login_url = '/login/'
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.movie_service = MovieService()
        self.user_service = UserService()
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        try:
            # Fetch only current user's ratings
            from ..repositories.ratings_repository import RatingsRepository
            ratings_repo = RatingsRepository()
            user_ratings = {}
            for r in ratings_repo.find_by_user(self.request.user.id):
                mid = r.get('movie_id')
                rating = r.get('rating', 0)
                if mid is not None:
                    user_ratings[int(mid)] = int(rating)

            rated_movies = []
            for mid, rating in user_ratings.items():
                m = self.movie_service.get_movie(mid)
                if m:
                    m['user_rating'] = rating
                    rated_movies.append(m)

            context.update({
                'rated_movies': rated_movies,
            })
        except Exception as e:
            logger.error(f"Error loading my_ratings for user {self.request.user.id}: {e}")
            context.update({
                'rated_movies': [],
            })
        
        return context


class RateMovieView(LoginRequiredMixin, View):
    """Create or update a user's rating for a movie (1-10)"""
    login_url = '/login/'
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.user_service = UserService()
    
    def post(self, request, movie_id):
        try:
            rating = int(request.POST.get('rating', 0))
        except ValueError:
            rating = 0

        if rating < 1 or rating > 10:
            return JsonResponse({'success': False, 'message': 'Rating must be between 1 and 10'}, status=400)

        try:
            success = self.user_service.save_user_rating(request.user.id, movie_id, rating)
            
            if not success:
                return JsonResponse({'success': False, 'message': 'Error saving rating'}, status=500)

            # AJAX?
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.content_type == 'application/json':
                return JsonResponse({'success': True, 'message': 'Rating saved', 'rating': rating})

            messages.success(request, 'Your rating has been saved.')
            referer = request.META.get('HTTP_REFERER')
            if referer:
                return redirect(referer)
            return redirect('movie_detail', movie_id=movie_id)
            
        except Exception as e:
            logger.error(f"Error saving rating for user {request.user.id} movie {movie_id}: {e}")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.content_type == 'application/json':
                return JsonResponse({'success': False, 'message': 'Error saving rating'}, status=500)
            messages.error(request, 'Could not save your rating. Please try again.')
            return redirect('movie_detail', movie_id=movie_id)


class DeleteRatingView(LoginRequiredMixin, View):
    """Delete a specific rating for the current user."""
    login_url = '/login/'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.user_service = UserService()

    def post(self, request, movie_id):
        success = self.user_service.delete_user_rating(request.user.id, movie_id)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.content_type == 'application/json':
            if success:
                return JsonResponse({'success': True})
            return JsonResponse({'success': False}, status=400)
        if success:
            messages.success(request, 'Rating removed.')
        else:
            messages.error(request, 'Could not remove rating.')
        return redirect('my_ratings')


class ReviewView(LoginRequiredMixin, View):
    """Create, update, or delete a review for a movie."""
    login_url = '/login/'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.user_service = UserService()

    def post(self, request, movie_id):
        # Support method override for delete
        if request.POST.get('_method') == 'delete':
            ok = self.user_service.delete_review(request.user.id, movie_id)
            if ok:
                messages.success(request, 'Review deleted.')
            else:
                messages.error(request, 'Could not delete review.')
            return redirect('movie_detail', movie_id=movie_id)

        # Create or update review
        text = request.POST.get('text', '').strip()
        if not text:
            messages.error(request, 'Review cannot be empty.')
            return redirect('movie_detail', movie_id=movie_id)
        ok = self.user_service.save_review(request.user.id, movie_id, text)
        if ok:
            messages.success(request, 'Review saved.')
        else:
            messages.error(request, 'Could not save review.')
        return redirect('movie_detail', movie_id=movie_id)

    def delete(self, request, movie_id):
        # Delete review (AJAX-friendly)
        ok = self.user_service.delete_review(request.user.id, movie_id)
        if ok:
            return JsonResponse({'success': True})
        return JsonResponse({'success': False}, status=400)


class RegisterView(TemplateView):
    """Register a new user"""
    template_name = 'register.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = UserCreationForm()
        return context
    
    def post(self, request):
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, "Account created successfully! You can now log in.")
            return redirect('login')
        
        return render(request, 'register.html', {'form': form})


class CustomLogoutView(View):
    """Custom logout view that redirects to home page with a message"""
    
    def post(self, request):
        from django.contrib.auth import logout
        logout(request)
        messages.success(request, "You have been successfully logged out.")
        return redirect('home')


class DeleteAccountView(LoginRequiredMixin, View):
    """Delete the current user's profile and related data."""
    login_url = '/login/'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.user_service = UserService()

    def post(self, request):
        success = self.user_service.delete_account(request.user)
        from django.contrib.auth import logout as django_logout
        if success:
            django_logout(request)
            messages.success(request, "Your account has been deleted.")
            return redirect('home')
        messages.error(request, "Could not delete your account. Please try again later.")
        return redirect('profile')


class LandingView(TemplateView):
    """Landing page view"""
    template_name = 'landing.html'


class PreferencesView(LoginRequiredMixin, TemplateView):
    """Collect initial genre preferences from the user."""
    template_name = 'preferences.html'
    login_url = '/login/'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.movie_service = MovieService()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Fetch TMDB genres via MovieService and expose as label list
        try:
            genre_map = self.movie_service.get_movie_genres_map()
            genres_sorted = sorted(genre_map.values())
            context.update({ 'genre_options': [{ 'label': g } for g in genres_sorted] })
        except Exception:
            context.update({ 'genre_options': [] })
        return context

    def post(self, request):
        try:
            selected = request.POST.getlist('genres')
            # Keep between 0..5 as suggested
            selected = selected[:5]
            cache.set(f"user_selected_genres_{request.user.id}", selected, timeout=60*60*24)
            messages.success(request, 'Preferences saved.')
            return redirect('home')
        except Exception as e:
            logger.error(f"Error saving preferred genres for user {request.user.id}: {e}")
            messages.error(request, 'Could not save your preferences. Please try again.')
            return redirect('preferences')


class ForYouView(LoginRequiredMixin, TemplateView):
    """Genre-based cold-start recommendations for the user."""
    template_name = 'for_you.html'
    login_url = '/login/'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.movie_service = MovieService()
        self.user_service = UserService()

    def _cosine_similarity(self, user_genres: list[str], movie_genres: list[str]) -> float:
        try:
            if not user_genres or not movie_genres:
                return 0.0
            user_set = set(g.lower() for g in user_genres)
            movie_set = set(g.lower() for g in movie_genres)
            overlap = len(user_set & movie_set)
            if overlap == 0:
                return 0.0
            import math
            return overlap / (math.sqrt(len(user_set)) * math.sqrt(len(movie_set)))
        except Exception:
            return 0.0

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        try:
            # Load user selected genres from cache
            selected = cache.get(f"user_selected_genres_{self.request.user.id}") or []

            # Cache recommendations for one hour keyed by selection
            cache_key = f"for_you_{self.request.user.id}_{'_'.join(sorted([s.lower() for s in selected]))}"
            cached = cache.get(cache_key)
            if cached is not None:
                context.update({ 'recommendations': cached, 'selected_genres': selected })
                return context

            # Candidate pool
            candidates = self.movie_service.get_popular_movies(limit=200)

            scored = []
            for m in candidates:
                try:
                    movie_genres = m.get('genres', []) or []
                    sim = self._cosine_similarity(selected, movie_genres)
                    pop = float(m.get('vote_average', 0.0))
                    score = 0.8 * sim + 0.2 * (pop / 10.0)
                    scored.append((score, m))
                except Exception:
                    continue

            # Fallbacks if sparse input or no overlap
            if not selected:
                recommendations = candidates[:20]
            else:
                scored.sort(key=lambda t: t[0], reverse=True)
                top = [m for _s, m in scored[:20]]
                # If too few with signal, blend with popular
                if len(top) < 20:
                    seen = {m.get('id') for m in top}
                    for p in candidates:
                        if p.get('id') not in seen:
                            top.append(p)
                        if len(top) >= 20:
                            break
                recommendations = top

            cache.set(cache_key, recommendations, timeout=60*60)

            context.update({
                'recommendations': recommendations,
                'selected_genres': selected,
            })
        except Exception as e:
            logger.error(f"Error building for_you for user {self.request.user.id}: {e}")
            context.update({
                'recommendations': self.movie_service.get_popular_movies(limit=20),
                'selected_genres': [],
            })

        return context
