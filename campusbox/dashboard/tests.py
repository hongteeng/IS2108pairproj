from datetime import time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from menu.models import Meal, MealCategory, MenuItem, WeeklyMenu
from orders.models import Order, OrderItem, PickupPoint, PickupSlot

from .forms import MealForm, PickupSlotForm, WeeklyMenuForm

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

class MealDeleteTests(TestCase):
    def setUp(self):
        User.objects.create_user('staff1', password='Pass1234!', is_staff=True)
        self.client.login(username='staff1', password='Pass1234!')
        self.category = MealCategory.objects.create(name='Rice')

    def make_meal(self, name):
        return Meal.objects.create(
            name=name, description='Test', price_cents=500,
            calories=500, protein_g=30, carbs_g=60, fat_g=10,
            image_url='', category=self.category,
        )

    def test_meal_with_no_orders_can_be_deleted(self):
        meal = self.make_meal('Unordered Meal')
        response = self.client.post(reverse('dashboard:meal_delete', args=[meal.id]))
        self.assertRedirects(response, reverse('dashboard:meal_list'))
        self.assertFalse(Meal.objects.filter(id=meal.id).exists())

    def test_meal_with_orders_cannot_be_deleted(self):
        meal = self.make_meal('Ordered Meal')
        menu = WeeklyMenu.objects.create(week_start=timezone.localdate(), order_cutoff=timezone.now())
        item = MenuItem.objects.create(weekly_menu=menu, meal=meal, quantity_available=10)
        point = PickupPoint.objects.create(name='Library', location='Level 1')
        slot = PickupSlot.objects.create(
            pickup_point=point, day=timezone.localdate() + timedelta(days=1),
            start_time=time(12, 0), end_time=time(12, 30), capacity=20,
        )
        customer = User.objects.create_user('student1', password='Pass1234!')
        order = Order.objects.create(user=customer, pickup_slot=slot, total_cents=500)
        OrderItem.objects.create(order=order, menu_item=item, quantity=1, price_at_purchase_cents=500)

        response = self.client.post(reverse('dashboard:meal_delete', args=[meal.id]))
        self.assertEqual(response.status_code, 200) #stays on the page, no redirect
        self.assertIn('cannot be deleted', response.context['error'])
        self.assertTrue(Meal.objects.filter(id=meal.id).exists())

def next_monday():
    today = timezone.localdate()
    return today + timedelta(days=7 - today.weekday()) #always a Monday in the future


class WeeklyMenuFormTests(TestCase):
    def form_data(self, **changes):
        monday = next_monday()
        data = {
            'week_start': monday.isoformat(),
            'order_cutoff': (monday - timedelta(days=1)).isoformat() + ' 23:59', #Sunday night before
        }
        data.update(changes)
        return data

    def test_valid_menu_is_accepted(self):
        self.assertTrue(WeeklyMenuForm(self.form_data()).is_valid())

    def test_start_date_must_be_a_monday(self):
        tuesday = next_monday() + timedelta(days=1)
        form = WeeklyMenuForm(self.form_data(week_start=tuesday.isoformat()))
        self.assertFalse(form.is_valid())
        self.assertIn('week_start', form.errors)

    def test_cutoff_must_be_before_the_week_starts(self):
        monday = next_monday()
        form = WeeklyMenuForm(self.form_data(order_cutoff=monday.isoformat() + ' 09:00'))
        self.assertFalse(form.is_valid())
        self.assertIn('order_cutoff', form.errors)

    def test_only_one_menu_per_week(self):
        WeeklyMenu.objects.create(week_start=next_monday(), order_cutoff=timezone.now())
        form = WeeklyMenuForm(self.form_data())
        self.assertFalse(form.is_valid())
        self.assertIn('week_start', form.errors)


class PickupSlotFormTests(TestCase):
    def form_data(self, **changes):
        data = {
            'day': next_monday().isoformat(), 'start_time': '12:00',
            'end_time': '12:30', 'capacity': 10,
        }
        data.update(changes)
        return data

    def test_valid_slot_is_accepted(self):
        self.assertTrue(PickupSlotForm(self.form_data()).is_valid())

    def test_weekend_is_rejected(self):
        saturday = next_monday() + timedelta(days=5)
        form = PickupSlotForm(self.form_data(day=saturday.isoformat()))
        self.assertFalse(form.is_valid())
        self.assertIn('day', form.errors)

    def test_past_date_is_rejected(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        form = PickupSlotForm(self.form_data(day=yesterday.isoformat()))
        self.assertFalse(form.is_valid())
        self.assertIn('day', form.errors)

    def test_end_time_must_be_after_start_time(self):
        form = PickupSlotForm(self.form_data(start_time='13:00', end_time='12:00'))
        self.assertFalse(form.is_valid())
        self.assertIn('end_time', form.errors)

    def test_capacity_must_be_at_least_one(self):
        form = PickupSlotForm(self.form_data(capacity=0))
        self.assertFalse(form.is_valid())
        self.assertIn('capacity', form.errors)


class StaffAccountsTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner1', password='Pass1234!', is_staff=True, is_superuser=True)
        self.staff = User.objects.create_user('staff1', password='Pass1234!', is_staff=True)
        self.student = User.objects.create_user('student1', password='Pass1234!')
        self.url = reverse('dashboard:staff_accounts')

    def new_staff_data(self, **changes):
        data = {
            'username': 'newstaff', 'email': 'newstaff@example.com',
            'password': 'Sup3rSecret!x', 'confirm_password': 'Sup3rSecret!x',
        }
        data.update(changes)
        return data

    def test_owner_can_open_the_page(self):
        self.client.login(username='owner1', password='Pass1234!')
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_normal_staff_is_sent_back_to_the_dashboard(self):
        self.client.login(username='staff1', password='Pass1234!')
        self.assertRedirects(self.client.get(self.url), reverse('dashboard:home'))

    def test_student_is_sent_to_staff_login(self):
        self.client.login(username='student1', password='Pass1234!')
        self.assertRedirects(self.client.get(self.url), reverse('dashboard:staff_login'))

    def test_owner_can_add_a_staff_account(self):
        self.client.login(username='owner1', password='Pass1234!')
        response = self.client.post(self.url, self.new_staff_data())
        self.assertRedirects(response, self.url)
        member = User.objects.get(username='newstaff')
        self.assertTrue(member.is_staff)
        self.assertFalse(member.is_superuser)
        self.assertTrue(member.check_password('Sup3rSecret!x')) #stored hashed, not as plain text
        self.assertNotEqual(member.password, 'Sup3rSecret!x')

    def test_normal_staff_cannot_add_a_staff_account(self):
        self.client.login(username='staff1', password='Pass1234!')
        self.client.post(self.url, self.new_staff_data())
        self.assertFalse(User.objects.filter(username='newstaff').exists())

    def test_duplicate_username_is_rejected(self):
        self.client.login(username='owner1', password='Pass1234!')
        response = self.client.post(self.url, self.new_staff_data(username='staff1'))
        self.assertEqual(response.status_code, 200) #stays on the page and shows the error
        self.assertEqual(User.objects.filter(username__iexact='staff1').count(), 1)

    def test_owner_can_deactivate_and_reactivate_staff(self):
        self.client.login(username='owner1', password='Pass1234!')
        self.client.post(self.url, {'toggle_id': self.staff.id})
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.is_active)
        self.client.post(self.url, {'toggle_id': self.staff.id})
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.is_active)

    def test_deactivated_staff_cannot_log_in(self):
        self.client.login(username='owner1', password='Pass1234!')
        self.client.post(self.url, {'toggle_id': self.staff.id})
        self.client.logout()
        self.assertFalse(self.client.login(username='staff1', password='Pass1234!'))

    def test_owner_cannot_be_deactivated(self):
        self.client.login(username='owner1', password='Pass1234!')
        response = self.client.post(self.url, {'toggle_id': self.owner.id})
        self.assertEqual(response.status_code, 404)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_active)

    def test_bad_id_gives_404_not_a_crash(self):
        self.client.login(username='owner1', password='Pass1234!')
        self.assertEqual(self.client.post(self.url, {'toggle_id': 'abc'}).status_code, 404)


class NewMenuDefaultsTests(TestCase):
    def setUp(self):
        User.objects.create_user('staff1', password='Pass1234!', is_staff=True)
        self.client.login(username='staff1', password='Pass1234!')
        self.form = self.client.get(reverse('dashboard:menu_add')).context['form']

    def test_new_menu_form_suggests_the_next_monday_and_a_night_before_cutoff(self):
        week_start = self.form.initial['week_start']
        cutoff = self.form.initial['order_cutoff']
        self.assertEqual(week_start.weekday(), 0) #a Monday
        self.assertGreater(week_start, timezone.localdate()) #in the future
        self.assertEqual(cutoff.date(), week_start - timedelta(days=1)) #the night before
        self.assertEqual((cutoff.hour, cutoff.minute), (23, 59))

    def test_the_suggested_dates_are_accepted_as_they_are(self):
        data = {
            'week_start': self.form.initial['week_start'].isoformat(),
            'order_cutoff': self.form.initial['order_cutoff'].strftime('%Y-%m-%d %H:%M'),
        }
        self.assertRedirects(self.client.post(reverse('dashboard:menu_add'), data), reverse('dashboard:menu_list'))
