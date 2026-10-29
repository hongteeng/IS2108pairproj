from django.urls import path
from . import views

app_name = 'menu'

urlpatterns = [ #list of functions to run depending on web address
    path('seed/', views.seed, name='seed'),
] #'seed' is address visiting it will point at functions views.seed. name is nickname