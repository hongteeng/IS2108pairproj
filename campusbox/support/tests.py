from datetime import time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from orders.models import Order, PickupPoint, PickupSlot

from .forms import StaffTicketForm
from .models import SupportTicket


class RefundLimitTests(TestCase): #refunds on one order can never add up to more than its total
    def setUp(self):
        user = User.objects.create_user('alice', password='Pass1234!')
        point = PickupPoint.objects.create(name='Library', location='Level 1')
        slot = PickupSlot.objects.create(
            pickup_point=point, day=timezone.localdate() + timedelta(days=1),
            start_time=time(12, 0), end_time=time(12, 30), capacity=20,
        )
        order = Order.objects.create(user=user, pickup_slot=slot, total_cents=1000, status='collected')
        self.first = SupportTicket.objects.create(user=user, order=order, issue_type='other', message='Cold food')
        self.second = SupportTicket.objects.create(user=user, order=order, issue_type='other', message='Missing drink')

    def form(self, ticket, refund):
        return StaffTicketForm({'status': 'resolved', 'refund_dollars': refund, 'staff_reply': 'Sorry'}, instance=ticket)

    def test_one_ticket_can_refund_up_to_the_order_total(self):
        self.assertTrue(self.form(self.first, '10.00').is_valid())
        self.assertFalse(self.form(self.first, '10.01').is_valid())

    def test_second_ticket_only_gets_what_is_left(self):
        first = self.form(self.first, '6.00')
        self.assertTrue(first.is_valid())
        first.save()
        self.assertFalse(self.form(self.second, '5.00').is_valid()) #6 + 5 would be more than 10
        self.assertTrue(self.form(self.second, '4.00').is_valid())
