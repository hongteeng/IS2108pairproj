from datetime import time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from orders.models import Order, PickupPoint, PickupSlot


class DeactivateAccountTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user('student1', email='s1@example.com', password='Pass1234!')
        self.url = reverse('accounts:deactivate_account')
        point = PickupPoint.objects.create(name='Library', location='Level 1')
        self.slot = PickupSlot.objects.create(
            pickup_point=point, day=timezone.localdate() + timedelta(days=1),
            start_time=time(12, 0), end_time=time(12, 30), capacity=20,
        )

    def make_order(self, status):
        return Order.objects.create(user=self.student, pickup_slot=self.slot, status=status, total_cents=500)

    def test_customer_without_open_orders_can_deactivate(self):
        self.client.login(username='student1', password='Pass1234!')
        response = self.client.post(self.url)
        self.assertRedirects(response, reverse('index'))
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_active)

    def test_deactivated_customer_cannot_log_in(self):
        self.client.login(username='student1', password='Pass1234!')
        self.client.post(self.url)
        self.assertFalse(self.client.login(username='student1', password='Pass1234!'))
        response = self.client.post(reverse('accounts:login'), {'username': 'student1', 'password': 'Pass1234!'})
        self.assertEqual(response.context['error'], 'Incorrect username or password.')

    def test_open_order_blocks_deactivation(self):
        self.make_order('confirmed')
        self.client.login(username='student1', password='Pass1234!')
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200) #stays on the page
        self.student.refresh_from_db()
        self.assertTrue(self.student.is_active)

    def test_collected_and_cancelled_orders_do_not_block(self):
        self.make_order('collected')
        self.make_order('cancelled')
        self.client.login(username='student1', password='Pass1234!')
        self.client.post(self.url)
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_active)

    def test_order_history_is_kept(self):
        self.make_order('collected')
        self.client.login(username='student1', password='Pass1234!')
        self.client.post(self.url)
        self.assertEqual(Order.objects.filter(user=self.student).count(), 1)

    def test_opening_the_page_changes_nothing(self):
        self.client.login(username='student1', password='Pass1234!')
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.student.refresh_from_db()
        self.assertTrue(self.student.is_active)

    def test_anonymous_visitor_is_sent_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('accounts:login'), response.url)

    def test_staff_cannot_use_the_customer_page(self):
        User.objects.create_user('staff1', password='Pass1234!', is_staff=True)
        self.client.login(username='staff1', password='Pass1234!')
        self.assertRedirects(self.client.post(self.url), reverse('dashboard:home'))
        self.assertTrue(User.objects.get(username='staff1').is_active)

class ChangePasswordTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('amy', password='OldPass123!')
        self.url = reverse('accounts:change_password')
        self.good = {'old_password': 'OldPass123!',
                     'new_password1': 'NewPass456!', 'new_password2': 'NewPass456!'}

    def test_must_be_logged_in(self):
        self.assertRedirects(self.client.get(self.url), f"{reverse('accounts:login')}?next={self.url}")

    def test_changes_password_and_stays_logged_in(self):
        self.client.login(username='amy', password='OldPass123!')
        self.assertRedirects(self.client.post(self.url, self.good), reverse('accounts:quiz'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewPass456!'))
        self.assertEqual(self.client.get(reverse('accounts:quiz')).status_code, 200)

    def test_wrong_old_password_is_refused(self):
        self.client.login(username='amy', password='OldPass123!')
        data = {**self.good, 'old_password': 'wrong'}
        self.assertEqual(self.client.post(self.url, data).status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('OldPass123!'))

    def test_mismatched_new_passwords_are_refused(self):
        self.client.login(username='amy', password='OldPass123!')
        data = {**self.good, 'new_password2': 'Different789!'}
        self.assertEqual(self.client.post(self.url, data).status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('OldPass123!'))