#!/usr/bin/env python
"""
Migration script to transition from procedural to object-oriented architecture
"""
import os
import sys
import django
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'movie_recommender.settings')
django.setup()

def backup_original_files():
    """Create backups of original files"""
    import shutil
    from datetime import datetime
    
    backup_dir = project_root / 'backup' / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    files_to_backup = [
        'movies/views.py',
        'movies/urls.py',
        'movies/movie_data.py',
        'movies/recommender.py',
        'movie_recommender/urls.py'
    ]
    
    for file_path in files_to_backup:
        if (project_root / file_path).exists():
            shutil.copy2(project_root / file_path, backup_dir / Path(file_path).name)
            print(f"Backed up {file_path} to {backup_dir}")
    
    print(f"Backup completed in {backup_dir}")

def update_urls():
    """Update URL configuration to use new class-based views"""
    # Update movies/urls.py
    urls_content = '''from django.urls import path
from . import views_new
from .views.movie_views import HomeView, MovieDetailView, MovieSearchView, MovieFilterAjaxView, ActorMoviesView
from .views.user_views import (
    WatchlistView, AddToWatchlistView, RemoveFromWatchlistView,
    ProfileView, MyRatingsView, RateMovieView,
    RegisterView, CustomLogoutView, LandingView
)

urlpatterns = [
    # Class-based views
    path('', HomeView.as_view(), name='home'),
    path('movie/<int:movie_id>/', MovieDetailView.as_view(), name='movie_detail'),
    path('movie/<int:movie_id>/rate/', RateMovieView.as_view(), name='rate_movie'),
    path('search/', views_new.search, name='search'),  # Keep legacy search for now
    path('filter/', MovieSearchView.as_view(), name='movie_filter'),
    path('filter/ajax/', MovieFilterAjaxView.as_view(), name='movie_filter_ajax'),
    path('watchlist/', WatchlistView.as_view(), name='watchlist'),
    path('add-to-watchlist/<int:movie_id>/', AddToWatchlistView.as_view(), name='add_to_watchlist'),
    path('remove-from-watchlist/<int:movie_id>/', RemoveFromWatchlistView.as_view(), name='remove_from_watchlist'),
    
    path('actor/<int:actor_id>/', ActorMoviesView.as_view(), name='actor_movies'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('my-ratings/', MyRatingsView.as_view(), name='my_ratings'),
    path('register/', RegisterView.as_view(), name='register'),
    path('logout/', CustomLogoutView.as_view(), name='custom_logout'),
    path('landing/', LandingView.as_view(), name='landing'),
]'''
    
    urls_file = project_root / 'movies' / 'urls.py'
    with open(urls_file, 'w') as f:
        f.write(urls_content)
    print("Updated movies/urls.py to use class-based views")
    
    # Update movie_recommender/urls.py
    main_urls_content = '''from django.urls import path, include
from django.contrib.auth import views as auth_views
from movies.views.user_views import RegisterView

urlpatterns = [
    # Remove admin path
    path('', include('movies.urls')),
    path('accounts/login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='/'), name='logout'),
    path('accounts/register/', RegisterView.as_view(), name='register'),
]'''
    
    main_urls_file = project_root / 'movie_recommender' / 'urls.py'
    with open(main_urls_file, 'w') as f:
        f.write(main_urls_content)
    print("Updated movie_recommender/urls.py to use class-based views")

def test_services():
    """Test that all services can be imported and instantiated"""
    try:
        from movies.services.movie_service import MovieService
        from movies.services.user_service import UserService
        
        
        # Test instantiation
        movie_service = MovieService()
        user_service = UserService()
        
        
        print("✅ All services imported and instantiated successfully")
        return True
        
    except Exception as e:
        print(f"❌ Error testing services: {e}")
        return False

def test_views():
    """Test that all views can be imported"""
    try:
        from movies.views.movie_views import HomeView, MovieDetailView, MovieSearchView
        from movies.views.user_views import WatchlistView, ProfileView
        
        print("✅ All views imported successfully")
        return True
        
    except Exception as e:
        print(f"❌ Error testing views: {e}")
        return False

def run_migration():
    """Run the complete migration process"""
    print("🚀 Starting migration to object-oriented architecture...")
    
    # Step 1: Backup original files
    print("\n📦 Step 1: Creating backups...")
    backup_original_files()
    
    # Step 2: Test services
    print("\n🧪 Step 2: Testing services...")
    if not test_services():
        print("❌ Service tests failed. Aborting migration.")
        return False
    
    # Step 3: Test views
    print("\n🧪 Step 3: Testing views...")
    if not test_views():
        print("❌ View tests failed. Aborting migration.")
        return False
    
    # Step 4: Update URLs
    print("\n🔗 Step 4: Updating URL configuration...")
    update_urls()
    
    print("\n✅ Migration completed successfully!")
    print("\n📋 Next steps:")
    print("1. Test the application thoroughly")
    print("2. Update any custom templates if needed")
    print("3. Run your test suite")
    print("4. Deploy to staging environment for testing")
    print("5. Once validated, remove old files and clean up")
    
    return True

if __name__ == '__main__':
    success = run_migration()
    sys.exit(0 if success else 1)
