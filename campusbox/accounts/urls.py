from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', views.login, name='login'),
    path('logout/', views.logout, name='logout'),
    path('quiz/', views.quiz, name='quiz'),
    path('deactivate/', views.deactivate_account, name='deactivate_account'),
    path('password/', views.change_password, name='change_password'),
]