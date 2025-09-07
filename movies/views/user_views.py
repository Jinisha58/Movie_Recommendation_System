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
from django.views.decorators.http import require_POST
from datetime import datetime
from typing import Dict, Any

from ..services.movie_service import MovieService
from ..services.user_service import UserService
from ..services.recommendation_service import RecommendationService

logger = logging.getLogger(__name__)


class WatchlistView(LoginRequiredMixin, TemplateView):
    """View user's watchlist with robust error handling and fallbacks"""
    template_name = 'watchlist.html'
    login_url = '/login/'
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.movie_service = MovieService()
        self.user_service = UserService()
    
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
            
            # If we couldn't fetch any movies due to API errors, show a specific message
            if not movies and watchlist_entries:
                messages.warning(self.request, "We're having trouble connecting to our movie database. Your watchlist is still saved, but we can't display the movies right now. Please try again later.")
            
            # If watchlist is empty or has very few movies, add some recommended movies
            recommended_movies = []
            if len(movies) < 5:
                try:
                    # Try to get recommendations from cache
                    rec_cache_key = f"user_recommendations_{self.request.user.id}"
                    recommended_movies = cache.get(rec_cache_key)
                    
                    if recommended_movies is None:
                        # Get some popular movies as recommendations
                        popular_movies = self.movie_service.get_popular_movies(limit=10)
                        
                        # Filter out movies already in watchlist
                        watchlist_ids = [m.get('id') for m in movies if m.get('id')]
                        recommended_movies = [m for m in popular_movies if m.get('id') not in watchlist_ids]
                        
                        # Limit to 5 recommendations
                        recommended_movies = recommended_movies[:5]
                        
                        # Cache recommendations for 1 hour
                        cache.set(rec_cache_key, recommended_movies, timeout=3600)
                except Exception as rec_error:
                    logger.error(f"Error getting recommendations: {rec_error}")
                    logger.error(traceback.format_exc())
                    recommended_movies = []
            
            context.update({
                'movies': movies,
                'recommended_movies': recommended_movies,
                'has_few_movies': len(movies) < 5 and len(recommended_movies) > 0
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


class RecommendationsView(LoginRequiredMixin, TemplateView):
    """Show personalized movie recommendations for the user"""
    template_name = 'recommendations.html'
    login_url = '/login/'
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.movie_service = MovieService()
        self.user_service = UserService()
        self.recommendation_service = RecommendationService()
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        try:
            import traceback
            from datetime import datetime
            
            # Get current date for filtering unreleased movies
            current_date = datetime.now().strftime('%Y-%m-%d')
            
            # Try to get recommendations from cache
            cache_key = f"user_recommendations_{self.request.user.id}"
            recommendations = cache.get(cache_key)
            
            if recommendations is None:
                # Get user's viewed movies and watchlist via service
                viewed_entries = self.user_service.get_user_viewed_movies(self.request.user.id, limit=1000)
                viewed_movie_ids = [item['movie_id'] for item in viewed_entries]
                watchlist_items = self.user_service.get_user_watchlist(self.request.user.id)
                watchlist_movie_ids = [item['movie_id'] for item in watchlist_items]
                
                # Combine all user movie interactions
                all_user_movie_ids = list(set(viewed_movie_ids + watchlist_movie_ids))
                
                # If user has no history, return popular movies
                if not all_user_movie_ids:
                    recommendations = self.movie_service.get_popular_movies(limit=20)
                    message = "Explore some movies to get personalized recommendations!"
                    recommendation_type = "popular"
                else:
                    # Get recommendations using cosine similarity based on user's movie history
                    recommendations = self.recommendation_service.get_cosine_similarity_recommendations(all_user_movie_ids, num_recommendations=20)
                    
                    # Filter out unreleased movies
                    recommendations = [
                        movie for movie in recommendations 
                        if movie.get('release_date', '') <= current_date
                    ]
                    
                    # If we don't have enough movies, supplement with popular movies
                    if len(recommendations) < 20:
                        popular_movies = self.movie_service.get_popular_movies(limit=20 - len(recommendations))
                        
                        # Filter out movies the user has already interacted with or that are already in recommendations
                        processed_movie_ids = set(all_user_movie_ids + [m['id'] for m in recommendations])
                        popular_movies = [
                            movie for movie in popular_movies 
                            if movie['id'] not in processed_movie_ids
                        ]
                        
                        recommendations.extend(popular_movies)
                        recommendations = recommendations[:20]
                    
                    message = " "
                    recommendation_type = "personalized"
                
                # Cache the recommendations for 1 hour
                cache.set(cache_key, recommendations, timeout=3600)
                
                logger.info(f"Generated {len(recommendations)} recommendations for user {self.request.user.id}")
            else:
                logger.info(f"Retrieved {len(recommendations)} recommendations from cache for user {self.request.user.id}")
                message = " "
                recommendation_type = "personalized"
            
            context.update({
                'recommendations': recommendations,
                'recommendation_type': recommendation_type,
                'message': message
            })
            
        except Exception as e:
            logger.error(f"Error generating recommendations for user {self.request.user.id}: {e}")
            logger.error(traceback.format_exc())
            messages.error(self.request, "An error occurred while generating recommendations. Please try again later.")
            
            # Fallback to popular movies
            popular_movies = self.movie_service.get_popular_movies(limit=20)
            context.update({
                'recommendations': popular_movies,
                'recommendation_type': 'popular',
                'message': "Popular movies (error occurred with personalized recommendations)"
            })
        
        return context


class ProfileView(LoginRequiredMixin, TemplateView):
    """User profile view"""
    template_name = 'profile.html'
    login_url = '/login/'
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.movie_service = MovieService()
        self.user_service = UserService()
        self.recommendation_service = RecommendationService()
    
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
            
            # Ratings-based recommendations
            ratings_recs = self.recommendation_service.get_recommendations_from_ratings(self.request.user.id, min_similarity=0.5, limit=20)
            
            context.update({
                'user': self.request.user,
                'viewed_count': stats['viewed_count'],
                'watchlist_count': stats['watchlist_count'],
                'ratings_count': stats['ratings_count'],
                'recent_movies': recent_movies,
                'rated_movies': rated_movies,
                'ratings_recommendations': ratings_recs
            })
            
        except Exception as e:
            logger.error(f"Error in profile view for user {self.request.user.id}: {e}")
            messages.error(self.request, "An error occurred while loading your profile. Please try again later.")
            context.update({'user': self.request.user})
        
        return context


class MyRatingsView(LoginRequiredMixin, TemplateView):
    """Dedicated page to show user's ratings and item-based collaborative filtering recommendations"""
    template_name = 'ratings.html'
    login_url = '/login/'
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.movie_service = MovieService()
        self.user_service = UserService()
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        try:
            from math import sqrt

            # Fetch all ratings from the database via repository
            from ..repositories.ratings_repository import RatingsRepository
            ratings_repo = RatingsRepository()
            all_ratings = list(ratings_repo.collection.find({}))
            user_ratings_dict = {}  # user_id -> {movie_id: rating}
            for r in all_ratings:
                uid = r['user_id']
                mid = r['movie_id']
                rating = r.get('rating', 0)
                user_ratings_dict.setdefault(uid, {})[mid] = rating

            # Get current user's ratings
            user_ratings = user_ratings_dict.get(self.request.user.id, {})
            rated_movies = []
            for mid, rating in user_ratings.items():
                m = self.movie_service.get_movie(mid)
                if m:
                    m['user_rating'] = rating
                    rated_movies.append(m)

            # Transpose ratings: movie_id -> {user_id: rating}
            movie_ratings = {}
            for uid, movies in user_ratings_dict.items():
                for mid, rating in movies.items():
                    movie_ratings.setdefault(mid, {})[uid] = rating

            # Compute similarity between movies using cosine similarity
            movie_sim = {}  # movie_id -> {movie_id: similarity}
            movie_ids = list(movie_ratings.keys())

            for i in range(len(movie_ids)):
                m1 = movie_ids[i]
                movie_sim.setdefault(m1, {})
                for j in range(i + 1, len(movie_ids)):
                    m2 = movie_ids[j]
                    users_in_common = set(movie_ratings[m1].keys()) & set(movie_ratings[m2].keys())
                    if not users_in_common:
                        continue
                    num = sum(movie_ratings[m1][u] * movie_ratings[m2][u] for u in users_in_common)
                    denom = sqrt(sum(movie_ratings[m1][u]**2 for u in users_in_common)) * \
                            sqrt(sum(movie_ratings[m2][u]**2 for u in users_in_common))
                    if denom > 0:
                        sim = num / denom
                        movie_sim[m1][m2] = sim
                        movie_sim.setdefault(m2, {})[m1] = sim

            # Generate recommendations for the user
            scores = {}

            for mid, rating in user_ratings.items():
                if rating < 4:
                    continue  # only consider movies the current user rated 4 or 5

                for similar_mid, sim in movie_sim.get(mid, {}).items():
                    if similar_mid in user_ratings:
                        continue  # skip movies already rated by the current user

                    # Only consider movies that have a high average rating in the system
                    similar_ratings = movie_ratings.get(similar_mid, {}).values()
                    if not any(r >= 4 for r in similar_ratings):
                        continue

                    avg_rating = sum(similar_ratings) / len(similar_ratings)
                    if avg_rating < 4:
                        continue  # skip if the system average rating is less than 4

                    # Add to score
                    scores[similar_mid] = scores.get(similar_mid, 0) + sim * rating

            # Sort recommended movies by score
            recommended_ids = sorted(scores, key=lambda x: scores[x], reverse=True)[:24]
            recommended_movies = [self.movie_service.get_movie(mid) for mid in recommended_ids if self.movie_service.get_movie(mid)]

            # Filter recommended movies to only include those with TMDB rating >= 4
            recommended_movies = [
                movie for movie in recommended_movies 
                if movie.get('vote_average', 0) >= 4
            ]

            context.update({
                'rated_movies': rated_movies,
                'ratings_recommendations': recommended_movies
            })
            # Expose repo for deletion endpoint usage
            self.ratings_repo = ratings_repo

        except Exception as e:
            logger.error(f"Error loading my_ratings for user {self.request.user.id}: {e}")
            context.update({
                'rated_movies': [],
                'ratings_recommendations': []
            })
        
        return context


class RateMovieView(LoginRequiredMixin, View):
    """Create or update a user's rating for a movie (1-5)"""
    login_url = '/login/'
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.user_service = UserService()
    
    def post(self, request, movie_id):
        try:
            rating = int(request.POST.get('rating', 0))
        except ValueError:
            rating = 0

        if rating < 1 or rating > 5:
            return JsonResponse({'success': False, 'message': 'Rating must be between 1 and 5'}, status=400)

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
            form.save()
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
