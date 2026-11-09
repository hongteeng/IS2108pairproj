from django.urls import path
from . import views

app_name = 'support'

urlpatterns = [
    path('order/<int:order_id>/report/', views.report_problem, name='report_problem'),
    path('', views.my_tickets, name='my_tickets'),
]