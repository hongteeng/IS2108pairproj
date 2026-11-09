from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', views.login, name='login'),
    path('logout/', views.logout, name='logout'),
    path('quiz/', views.quiz, name='quiz'),
    path('staff/customers/', views.staff_customers, name='staff_customers'),
    path('staff/customers/<int:user_id>/', views.staff_customer_detail, name='staff_customer_detail'),
]