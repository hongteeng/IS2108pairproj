from django.urls import path
from . import views

app_name = 'orders'

urlpatterns = [
    path('', views.order_history, name='order_history'),
    path('cart/', views.cart_detail, name='cart'),
    path('cart/add/<int:menu_item_id>/', views.add_to_cart, name='add_to_cart'),
    path('cart/update/<int:menu_item_id>/', views.update_cart, name='update_cart'),
    path('checkout/', views.checkout, name='checkout'),
    path('order/<int:order_id>/', views.order_detail, name='order_detail'),
    path('order/<int:order_id>/cancel/', views.cancel_order, name='cancel_order'),
]