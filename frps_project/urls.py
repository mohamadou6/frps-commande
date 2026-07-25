"""
URL configuration for frps_project project.
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import RedirectView

from accounts.views import LoginView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', RedirectView.as_view(pattern_name='catalogue:liste', permanent=False)),
    path('login/', LoginView.as_view(template_name='accounts/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('catalogue/', include('catalogue.urls')),
    path('panier/', include('commandes.urls')),
    path('paiements/', include('paiements.urls')),
    path('notifications/', include('notifications.urls')),
]
