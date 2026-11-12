from django.urls import path
from accounts import views as account_views
from menu import views as menu_views
from reviews import views as review_views
from support import views as support_views
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
    path('menus/<int:menu_id>/edit/', views.menu_edit, name='menu_edit'),
    path('pickups/', views.pickup_list, name='pickup_list'),
    path('pickups/add/', views.pickup_add, name='pickup_add'),
    path('pickups/<int:point_id>/', views.pickup_detail, name='pickup_detail'),
    path('orders/', views.order_list, name='order_list'),
    path('orders/<int:order_id>/', views.order_detail, name='order_detail'),
    path('inventory/', views.inventory, name='inventory'),
    path('seed/', menu_views.seed, name='seed'),
    path('customers/', account_views.staff_customers, name='customers'),
    path('customers/<int:user_id>/', account_views.staff_customer_detail, name='customer_detail'),
    path('reviews/', review_views.staff_reviews, name='reviews'),
    path('reviews/<int:review_id>/toggle/', review_views.staff_toggle_review, name='review_toggle'),
    path('support/', support_views.staff_tickets, name='tickets'),
    path('support/<int:ticket_id>/', support_views.staff_ticket_detail, name='ticket_detail'),
    path('packing/', views.packing_list, name='packing_list'),
]
