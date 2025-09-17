from django.urls import path
from .views.movie_views import HomeView, MovieDetailView, MovieSearchView, MovieFilterAjaxView, ActorMoviesView, SearchView
from .views.user_views import (
    WatchlistView, AddToWatchlistView, RemoveFromWatchlistView,
    ProfileView, MyRatingsView, RateMovieView,
    RegisterView, CustomLogoutView, LandingView, DeleteAccountView, DeleteRatingView, ReviewView,
    PreferencesView, ForYouView
)

urlpatterns = [
    
    path('', HomeView.as_view(), name='home'),
    path('movie/<int:movie_id>/', MovieDetailView.as_view(), name='movie_detail'),
    path('movie/<int:movie_id>/rate/', RateMovieView.as_view(), name='rate_movie'),
    path('movie/<int:movie_id>/review/', ReviewView.as_view(), name='review_movie'),
    path('search/', SearchView.as_view(), name='search'),
    path('filter/', MovieSearchView.as_view(), name='movie_filter'),
    path('filter/ajax/', MovieFilterAjaxView.as_view(), name='movie_filter_ajax'),
    path('watchlist/', WatchlistView.as_view(), name='watchlist'),
    path('add-to-watchlist/<int:movie_id>/', AddToWatchlistView.as_view(), name='add_to_watchlist'),
    path('remove-from-watchlist/<int:movie_id>/', RemoveFromWatchlistView.as_view(), name='remove_from_watchlist'),
    path('actor/<int:actor_id>/', ActorMoviesView.as_view(), name='actor_movies'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('profile/delete/', DeleteAccountView.as_view(), name='delete_account'),
    path('my-ratings/', MyRatingsView.as_view(), name='my_ratings'),
    path('my-ratings/delete/<int:movie_id>/', DeleteRatingView.as_view(), name='delete_rating'),
    path('register/', RegisterView.as_view(), name='register'),
    path('logout/', CustomLogoutView.as_view(), name='custom_logout'),
    path('landing/', LandingView.as_view(), name='landing'),
    path('preferences/', PreferencesView.as_view(), name='preferences'),
    path('for-you/', ForYouView.as_view(), name='for_you'),
]