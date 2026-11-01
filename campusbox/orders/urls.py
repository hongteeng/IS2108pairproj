from django.urls import path
from . import views

app_name = 'orders'

urlpatterns = [
    path('cart/', views.cart_detail, name='cart'),
    path('cart/add/<int:menu_item_id>/', views.add_to_cart, name='add_to_cart'),
    path('cart/update/<int:menu_item_id>/', views.update_cart, name='update_cart'),
]