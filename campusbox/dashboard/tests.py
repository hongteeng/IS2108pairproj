from datetime import time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from menu.models import Meal, MealCategory, MenuItem, WeeklyMenu
from orders.models import Order, OrderItem, PickupPoint, PickupSlot

from .forms import MealForm

class PackingListTests(TestCase):
    def setUp(self): #runs before every test, builds a small fake database
        self.staff = User.objects.create_user('staff1', password='Pass1234!', is_staff=True)
        category = MealCategory.objects.create(name='Rice')
        meal = Meal.objects.create(
            name='Chicken Rice Box', description='Test', price_cents=500,
            calories=500, protein_g=30, carbs_g=60, fat_g=10,
            image_url='', category=category,
        )
        menu = WeeklyMenu.objects.create(week_start=timezone.localdate(), order_cutoff=timezone.now())
        self.item = MenuItem.objects.create(weekly_menu=menu, meal=meal, quantity_available=50)
        point = PickupPoint.objects.create(name='Library', location='Level 1')
        self.slot = PickupSlot.objects.create(
            pickup_point=point, day=timezone.localdate() + timedelta(days=1),
            start_time=time(12, 0), end_time=time(12, 30), capacity=20,
        )
        customer = User.objects.create_user('student1', password='Pass1234!')
        self.make_order(customer, 'confirmed', 2)
        self.make_order(customer, 'preparing', 3)
        self.make_order(customer, 'cancelled', 5)

    def make_order(self, user, status, quantity):
        order = Order.objects.create(user=user, pickup_slot=self.slot, status=status, total_cents=500 * quantity)
        OrderItem.objects.create(order=order, menu_item=self.item, quantity=quantity, price_at_purchase_cents=500)

    def test_packing_list_adds_up_orders_and_skips_cancelled(self):
        self.client.login(username='staff1', password='Pass1234!')
        response = self.client.get(reverse('dashboard:packing_list'))
        self.assertEqual(response.status_code, 200)
        groups = response.context['groups']
        self.assertEqual(len(groups), 1)
        rows = list(groups[0]['items'])
        self.assertEqual(rows[0]['menu_item__meal__name'], 'Chicken Rice Box')
        self.assertEqual(rows[0]['total'], 5) #2 confirmed + 3 preparing, the 5 cancelled are left out

class StaffMiddlewareTests(TestCase): #create 2 fake users, staff and stuydent to test dashboard access
    def setUp(self):
        self.staff = User.objects.create_user('staff1', password='Pass1234!', is_staff=True)
        self.student = User.objects.create_user('student1', password='Pass1234!')

    def test_anonymous_visitor_is_sent_to_staff_login(self):
        response = self.client.get('/dashboard/')
        self.assertRedirects(response, reverse('dashboard:staff_login'))

    def test_logged_in_student_is_sent_to_staff_login(self):
        self.client.login(username='student1', password='Pass1234!')
        response = self.client.get('/dashboard/')
        self.assertRedirects(response, reverse('dashboard:staff_login'))

    def test_staff_can_open_the_dashboard(self):
        self.client.login(username='staff1', password='Pass1234!')
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)

    def test_staff_login_page_is_open_to_everyone(self):
        response = self.client.get('/dashboard/login/')
        self.assertEqual(response.status_code, 200)

class MealFormTests(TestCase):
    def setUp(self):
        self.category = MealCategory.objects.create(name='Rice')

    def form_data(self, **changes): #a valid set of answers, we change one thing per test
        data = {
            'name': 'Chicken Rice Box', 'description': 'Test', 'price': '6.50',
            'calories': 500, 'protein_g': 30, 'carbs_g': 60, 'fat_g': 10,
            'image_url': 'x', 'category': self.category.id, 'is_active': True,
        }
        data.update(changes)
        return data

    def test_price_in_dollars_is_saved_as_cents(self):
        form = MealForm(self.form_data())
        self.assertTrue(form.is_valid())
        meal = form.save()
        self.assertEqual(meal.price_cents, 650)

    def test_zero_price_is_rejected(self):
        form = MealForm(self.form_data(price='0'))
        self.assertFalse(form.is_valid())
        self.assertIn('price', form.errors)

    def test_negative_price_is_rejected(self):
        form = MealForm(self.form_data(price='-3'))
        self.assertFalse(form.is_valid())
        self.assertIn('price', form.errors)

    def test_negative_calories_are_rejected(self):
        form = MealForm(self.form_data(calories=-100))
        self.assertFalse(form.is_valid())
        self.assertIn('calories', form.errors)