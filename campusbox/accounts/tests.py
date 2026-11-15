from datetime import datetime, time, timedelta
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.forms import RULES_BROKEN, RegisterForm
from menu.models import Meal, MealCategory, MenuItem, WeeklyMenu
from orders.models import Order, PickupPoint, PickupSlot
from reviews.models import Review
from support.models import SupportTicket


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
        self.assertRedirects(self.client.post(self.url, self.good), reverse('accounts:my_account'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewPass456!'))
        self.assertEqual(self.client.get(reverse('accounts:my_account')).status_code, 200)

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


class StaffPasswordAndReactivateTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('staff1', password='OldPass123!', is_staff=True)
        self.customer = User.objects.create_user('amy', password='Pass1234!', is_active=False)

    def test_staff_go_back_to_their_account_page_after_changing_password(self):
        self.client.login(username='staff1', password='OldPass123!')
        data = {'old_password': 'OldPass123!', 'new_password1': 'NewPass456!', 'new_password2': 'NewPass456!'}
        self.assertRedirects(self.client.post(reverse('accounts:change_password'), data), reverse('dashboard:my_account'))

    def test_staff_can_reactivate_a_customer(self):
        self.client.login(username='staff1', password='OldPass123!')
        url = reverse('dashboard:customer_detail', args=[self.customer.id])
        self.assertRedirects(self.client.post(url), url)
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.is_active)
        self.assertTrue(self.client.login(username='amy', password='Pass1234!'))


class MyAccountPageTests(TestCase): #the avatar opens My account, which holds password and deactivate
    def setUp(self):
        User.objects.create_user('amy', email='amy@example.com', password='Pass1234!')
        User.objects.create_user('staff1', password='Pass1234!', is_staff=True)
        self.url = reverse('accounts:my_account')

    def test_must_be_logged_in(self):
        self.assertRedirects(self.client.get(self.url), f"{reverse('accounts:login')}?next={self.url}")

    def test_shows_details_and_both_links(self):
        self.client.login(username='amy', password='Pass1234!')
        response = self.client.get(self.url)
        self.assertContains(response, '<title>My account · CampusBox</title>', html=True)
        self.assertContains(response, 'amy@example.com')
        self.assertContains(response, f'href="{reverse("accounts:change_password")}"')
        self.assertContains(response, f'href="{reverse("accounts:deactivate_account")}"')

    def test_staff_are_sent_to_the_staff_account_page(self):
        self.client.login(username='staff1', password='Pass1234!')
        self.assertRedirects(self.client.get(self.url), reverse('dashboard:my_account'))


class PasswordRulesTests(TestCase): #Sign up and Add staff list the same password rules as Change password
    RULE = 'too similar to your other personal information'

    def broken_rules(self, form):
        return [rule['text'] for rule in form.password_rules() if rule['passed'] is False]

    def test_password_too_like_the_username_is_refused(self):
        data = {'username': 'amyliew', 'email': 'amy@example.com', 'password': 'amyliew1', 'confirm_password': 'amyliew1'}
        form = RegisterForm(data)
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors['password'], [RULES_BROKEN])
        broken = self.broken_rules(form)
        self.assertEqual(len(broken), 1)
        self.assertIn(self.RULE, broken[0])

    def test_sign_up_marks_each_rule(self):
        data = {'username': 'amy', 'email': 'amy@example.com', 'password': 'Ab1!', 'confirm_password': 'Ab1!'}
        response = self.client.post(reverse('accounts:register'), data)
        self.assertContains(response, '<li class="text-danger">✗', count=1)  #only too short
        self.assertContains(response, '<li class="text-success">✓', count=3)
        self.assertContains(response, 'follow the rules marked ✗.', count=1)  #the apostrophe is escaped in HTML


class DemoDataTests(TestCase): #python manage.py demo_data should give dates that make sense
    def setUp(self):
        category = MealCategory.objects.create(name='Rice')
        today = timezone.localdate()
        week_start = today + timedelta(days=7 - today.weekday()) #next Monday, like Reset demo data
        menu = WeeklyMenu.objects.create(
            week_start=week_start,
            order_cutoff=timezone.make_aware(datetime.combine(week_start - timedelta(days=1), time(23, 59))),
        )
        for n in range(4):
            meal = Meal.objects.create(name=f'Meal {n}', description='Test', price_cents=500, calories=500,
                                       protein_g=20, carbs_g=50, fat_g=10, image_url='', category=category)
            MenuItem.objects.create(weekly_menu=menu, meal=meal, quantity_available=30)
        point = PickupPoint.objects.create(name='Library', location='Level 1')
        for days in (1, 2):
            PickupSlot.objects.create(pickup_point=point, day=week_start + timedelta(days=days),
                                      start_time=time(12, 0), end_time=time(13, 0), capacity=20)
        call_command('demo_data', customers=8, orders=20, stdout=StringIO())

    def test_collected_orders_are_in_the_past_and_new_ones_in_the_future(self):
        today = timezone.localdate()
        self.assertTrue(Order.objects.filter(status='collected').exists())
        self.assertTrue(Order.objects.filter(status='confirmed').exists())
        for order in Order.objects.select_related('pickup_slot', 'user'):
            if order.status in ('collected', 'ready'):
                self.assertLess(order.pickup_slot.day, today)
            if order.status == 'confirmed':
                self.assertGreaterEqual(order.pickup_slot.day, today)
            self.assertLessEqual(order.created_at, timezone.now())
            self.assertLessEqual(order.user.date_joined, order.created_at) #nobody ordered before signing up

    def test_reviews_and_tickets_come_after_the_pickup(self):
        for review in Review.objects.all():
            self.assertLessEqual(review.created_at, timezone.now())
        for ticket in SupportTicket.objects.select_related('order__pickup_slot'):
            self.assertGreaterEqual(timezone.localtime(ticket.created_at).date(), ticket.order.pickup_slot.day)
            self.assertLessEqual(ticket.created_at, timezone.now())


class StaffCustomerOrdersPagesTests(TestCase): #the Orders table on a customer's staff page shows 10 at a time
    def setUp(self):
        User.objects.create_user('staff1', password='Pass1234!', is_staff=True)
        self.client.login(username='staff1', password='Pass1234!')
        self.customer = User.objects.create_user('amy', password='Pass1234!')
        point = PickupPoint.objects.create(name='Library', location='Level 1')
        slot = PickupSlot.objects.create(pickup_point=point, day=timezone.localdate() + timedelta(days=1),
                                         start_time=time(12, 0), end_time=time(12, 30), capacity=50)
        self.orders = [Order.objects.create(user=self.customer, pickup_slot=slot, total_cents=500) for _ in range(12)]
        self.url = reverse('dashboard:customer_detail', args=[self.customer.id])

    def test_ten_newest_orders_first_then_the_rest(self):
        response = self.client.get(self.url)
        newest_first = [order.id for order in reversed(self.orders)]
        self.assertEqual([order.id for order in response.context['orders']], newest_first[:10])
        self.assertContains(response, 'Showing 1–10 of 12 orders')
        second = self.client.get(self.url, {'orders_page': 2}).context['orders']
        self.assertEqual([order.id for order in second], newest_first[10:])
