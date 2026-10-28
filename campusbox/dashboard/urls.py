from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.home, name='home'),
        path('login/', views.staff_login, name='staff_login'),
]