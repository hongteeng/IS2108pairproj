from django.urls import path
from . import views

app_name = 'reviews'

urlpatterns = [
    path('meal/<int:meal_id>/', views.add_review, name='add_review'),
    path('staff/', views.staff_reviews, name='staff_reviews'),
    path('staff/<int:review_id>/toggle/', views.staff_toggle_review, name='staff_toggle_review'),
]