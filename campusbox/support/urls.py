from django.urls import path
from . import views

app_name = 'support'

urlpatterns = [
    path('order/<int:order_id>/report/', views.report_problem, name='report_problem'),
    path('', views.my_tickets, name='my_tickets'),
    path('staff/', views.staff_tickets, name='staff_tickets'),
    path('staff/<int:ticket_id>/', views.staff_ticket_detail, name='staff_ticket_detail'),
]