from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.home, name='home'),
        path('login/', views.staff_login, name='staff_login'),
        path('meals/', views.meal_list, name='meal_list'),
        path('meals/add/', views.meal_add, name='meal_add'),
        path('meals/<int:meal_id>/edit/', views.meal_edit, name='meal_edit'),
        path('meals/<int:meal_id>/delete/', views.meal_delete, name='meal_delete'),
        path('menus/', views.menu_list, name='menu_list'),
        path('menus/add/', views.menu_add, name='menu_add'),
        path('menus/<int:menu_id>/', views.menu_detail, name='menu_detail'),
]

