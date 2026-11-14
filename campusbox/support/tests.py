from datetime import time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
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


class MyReportsListTests(TestCase): #filters and pages on the student's My reports page
    def setUp(self):
        self.student = User.objects.create_user('student1', password='Pass1234!')
        other = User.objects.create_user('student2', password='Pass1234!')
        point = PickupPoint.objects.create(name='Library', location='Level 1')
        slot = PickupSlot.objects.create(pickup_point=point, day=timezone.localdate() + timedelta(days=1),
                                         start_time=time(12, 0), end_time=time(12, 30), capacity=20)
        self.order = Order.objects.create(user=self.student, pickup_slot=slot, total_cents=1000, status='collected')
        for status in ['open', 'resolved', 'rejected']:
            SupportTicket.objects.create(user=self.student, order=self.order, issue_type='other', message=status, status=status)
        other_order = Order.objects.create(user=other, pickup_slot=slot, total_cents=1000, status='collected')
        SupportTicket.objects.create(user=other, order=other_order, issue_type='other', message='not mine')
        self.client.login(username='student1', password='Pass1234!')

    def messages_shown(self, **params):
        return [ticket.message for ticket in self.client.get(reverse('support:my_tickets'), params).context['page_obj']]

    def test_only_my_reports_newest_first(self):
        self.assertEqual(self.messages_shown(), ['rejected', 'resolved', 'open'])

    def test_status_filter(self):
        self.assertEqual(self.messages_shown(show='open'), ['open'])
        self.assertEqual(self.messages_shown(show='resolved'), ['resolved'])

    def test_ten_per_page(self):
        for number in range(9):
            SupportTicket.objects.create(user=self.student, order=self.order, issue_type='other', message=str(number))
        self.assertEqual(len(self.messages_shown()), 10)
        self.assertEqual(len(self.messages_shown(page=2)), 2)
