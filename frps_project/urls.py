"""
URL configuration for frps_project project.
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import RedirectView

from accounts.views import LoginView
from frps_project import pwa

urlpatterns = [
    path('admin/', admin.site.urls),
    # Enveloppe PWA : sw.js et manifest doivent être servis depuis la racine du site.
    path('sw.js', pwa.service_worker, name='service_worker'),
    path('manifest.webmanifest', pwa.manifeste, name='manifeste'),
    path('hors-ligne/', pwa.hors_ligne, name='hors_ligne'),
    path('', RedirectView.as_view(pattern_name='catalogue:liste', permanent=False)),
    path('login/', LoginView.as_view(template_name='accounts/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('catalogue/', include('catalogue.urls')),
    path('panier/', include('commandes.urls')),
    path('paiements/', include('paiements.urls')),
    path('notifications/', include('notifications.urls')),
    path('statistiques/', include('statistiques.urls')),
]
