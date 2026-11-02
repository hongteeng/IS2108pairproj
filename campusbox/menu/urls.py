from django.urls import path
from . import views

app_name = 'menu'

urlpatterns = [ #list of functions to run depending on web address
    path('seed/', views.seed, name='seed'),
    path('meal/<int:meal_id>/', views.meal_detail, name='meal_detail'),
    path('', views.weekly_menu, name='weekly_menu'),
] #'seed' is address visiting it will point at functions views.seed. name is nickname