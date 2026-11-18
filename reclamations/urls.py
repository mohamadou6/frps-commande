from django.urls import path

from . import views

app_name = "reclamations"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("nouvelle/", views.nouvelle, name="nouvelle"),
    path("<int:reclamation_id>/", views.detail, name="detail"),
    path("<int:reclamation_id>/repondre/", views.repondre, name="repondre"),
    path("photo/<int:photo_id>/", views.photo, name="photo"),
]
