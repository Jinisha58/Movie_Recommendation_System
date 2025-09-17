from django.urls import path, include
from django.contrib.auth import views as auth_views
from movies.views.user_views import RegisterView

urlpatterns = [
    
    path('', include('movies.urls')),
    path('accounts/login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login_alias'),
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='/'), name='logout'),
    path('accounts/register/', RegisterView.as_view(), name='register'),
]
