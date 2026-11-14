import shutil
import tempfile
from datetime import time, timedelta
from io import BytesIO

from PIL import Image
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from menu.models import Meal, MealCategory, MenuItem, WeeklyMenu
from orders.models import Order, OrderItem, PickupPoint, PickupSlot

from .forms import MealForm, PickupSlotForm, WeeklyMenuForm
from .roles import HR, OWNER, STAFF, role_of, set_role

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
        self.customer = customer

    def make_order(self, user, status, quantity, slot=None):
        order = Order.objects.create(user=user, pickup_slot=slot or self.slot, status=status, total_cents=500 * quantity)
        OrderItem.objects.create(order=order, menu_item=self.item, quantity=quantity, price_at_purchase_cents=500)

    def make_slot(self, days_ahead, hour, name='Library'):
        point = PickupPoint.objects.get_or_create(name=name, defaults={'location': 'Level 1'})[0]
        return PickupSlot.objects.create(pickup_point=point, day=timezone.localdate() + timedelta(days=days_ahead),
                                         start_time=time(hour, 0), end_time=time(hour + 1, 0), capacity=20)

    def get(self, **params):
        self.client.login(username='staff1', password='Pass1234!')
        return self.client.get(reverse('dashboard:packing_list'), params)

    def test_packing_list_adds_up_orders_and_skips_cancelled(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        cards = response.context['cards']
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]['totals'], [('Chicken Rice Box', 5)]) #2 confirmed + 3 preparing, the 5 cancelled are left out
        self.assertEqual(len(cards[0]['bags']), 2) #one bag per order still to make

    def test_opens_on_the_first_day_with_orders(self):
        later = self.make_slot(3, 12)
        self.make_order(self.customer, 'confirmed', 1, later)
        response = self.get()
        self.assertEqual(response.context['day'], self.slot.day)
        self.assertEqual(response.context['days'], [self.slot.day, later.day])
        self.assertEqual(self.get(day=later.day.isoformat()).context['day'], later.day)
        self.assertEqual(self.get(day='not-a-date').context['day'], self.slot.day) #a bad date falls back

    def test_cook_table_splits_lunch_and_dinner(self):
        self.make_order(self.customer, 'confirmed', 4, self.make_slot(1, 18))
        response = self.get()
        row = response.context['cook'][0]
        self.assertEqual((row['lunch'], row['dinner'], row['total']), (5, 4, 9))
        totals = (response.context['lunch_count'], response.context['dinner_count'], response.context['meal_count'])
        self.assertEqual(totals, (5, 4, 9)) #the All meals row
        self.assertContains(response, 'All meals')

    def test_slots_can_be_collapsed_and_start_open(self):
        self.make_order(self.customer, 'confirmed', 1, self.make_slot(1, 18))
        self.assertContains(self.get(), '<details open>', count=2) #lunch and dinner, both expanded

    def test_more_slots_do_not_mean_more_queries(self):
        self.client.login(username='staff1', password='Pass1234!')
        with CaptureQueriesContext(connection) as one_slot:
            self.client.get(reverse('dashboard:packing_list'))
        for name in ('UTown', 'Sheares'): #two more pickup points on the same day
            self.make_order(self.customer, 'confirmed', 1, self.make_slot(1, 12, name))
        with CaptureQueriesContext(connection) as three_slots:
            response = self.client.get(reverse('dashboard:packing_list'))
        self.assertEqual(len(response.context['cards']), 3)
        self.assertEqual(len(three_slots), len(one_slot)) #the whole day is fetched in one query

    def test_nothing_to_pack(self):
        Order.objects.update(status='collected')
        self.assertContains(self.get(), 'Nothing to pack right now.')

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
        self.assertNotContains(response, 'class="btn btn-danger"') #no Delete button once it has failed
        self.assertContains(response, 'Edit meal')

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
        self.add_url = reverse('dashboard:staff_account_add')

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
        response = self.client.post(self.add_url, self.new_staff_data())
        self.assertRedirects(response, self.url)
        member = User.objects.get(username='newstaff')
        self.assertTrue(member.is_staff)
        self.assertFalse(member.is_superuser)
        self.assertTrue(member.check_password('Sup3rSecret!x')) #stored hashed, not as plain text
        self.assertNotEqual(member.password, 'Sup3rSecret!x')

    def test_normal_staff_cannot_add_a_staff_account(self):
        self.client.login(username='staff1', password='Pass1234!')
        self.client.post(self.add_url, self.new_staff_data())
        self.assertFalse(User.objects.filter(username='newstaff').exists())

    def test_duplicate_username_is_rejected(self):
        self.client.login(username='owner1', password='Pass1234!')
        response = self.client.post(self.add_url, self.new_staff_data(username='staff1'))
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

    def test_owner_cannot_deactivate_themselves(self):
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
        response = self.client.post(reverse('dashboard:menu_add'), data)
        menu = WeeklyMenu.objects.get(week_start=self.form.initial['week_start'])
        self.assertRedirects(response, reverse('dashboard:menu_detail', args=[menu.id])) #opens the new week


class CraftedPostTests(TestCase): #a POST with a made-up id should give "not found", not crash the page
    def setUp(self):
        User.objects.create_user('staff1', password='Pass1234!', is_staff=True)
        self.client.login(username='staff1', password='Pass1234!')
        self.menu = WeeklyMenu.objects.create(week_start=timezone.localdate(), order_cutoff=timezone.now())
        self.point = PickupPoint.objects.create(name='Library', location='Level 1')

    def test_inventory_with_bad_item_id_is_404(self):
        response = self.client.post(reverse('dashboard:inventory'), {'qty_abc': '5'})
        self.assertEqual(response.status_code, 404)

    def test_menu_detail_with_bad_remove_id_is_404(self):
        response = self.client.post(reverse('dashboard:menu_detail', args=[self.menu.id]), {'remove_id': 'abc'})
        self.assertEqual(response.status_code, 404)

    def test_slot_from_another_point_cannot_be_removed(self):
        other = PickupPoint.objects.create(name='Hall', location='Lobby')
        slot = PickupSlot.objects.create(
            pickup_point=other, day=timezone.localdate() + timedelta(days=1),
            start_time=time(12, 0), end_time=time(12, 30), capacity=20,
        )
        response = self.client.post(reverse('dashboard:pickup_detail', args=[self.point.id]), {'remove_id': str(slot.id)})
        self.assertEqual(response.status_code, 404)
        self.assertTrue(PickupSlot.objects.filter(id=slot.id).exists())


class StaffRoleTests(TestCase): #Owner, HR and Staff, see dashboard/roles.py
    def setUp(self):
        self.owner = User.objects.create_user('owner1', password='Pass1234!', is_staff=True, is_superuser=True)
        self.hr = User.objects.create_user('hr1', password='Pass1234!')
        set_role(self.hr, HR)
        self.staff = User.objects.create_user('staff1', password='Pass1234!', is_staff=True)
        self.url = reverse('dashboard:staff_accounts')
        self.add_url = reverse('dashboard:staff_account_add')

    def login(self, username):
        self.client.login(username=username, password='Pass1234!')

    def new_staff_data(self, **changes):
        data = {'username': 'newstaff', 'email': 'newstaff@example.com',
                'password': 'Sup3rSecret!x', 'confirm_password': 'Sup3rSecret!x'}
        data.update(changes)
        return data

    def test_hr_can_open_staff_accounts_and_sees_the_link(self):
        self.login('hr1')
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertContains(self.client.get(reverse('dashboard:home')), 'Staff accounts')

    def test_plain_staff_cannot_open_the_add_page(self):
        self.login('staff1')
        self.assertRedirects(self.client.get(self.add_url), reverse('dashboard:home'))

    def test_hr_add_page_has_no_role_choice(self):
        self.login('hr1')
        response = self.client.get(self.add_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('role', response.context['form'].fields)

    def test_plain_staff_do_not_see_the_link(self):
        self.login('staff1')
        self.assertNotContains(self.client.get(reverse('dashboard:home')), 'Staff accounts')

    def test_hr_always_adds_plain_staff(self):
        self.login('hr1')
        self.client.post(self.add_url, self.new_staff_data(role=OWNER)) #HR's form has no role field, so this is ignored
        self.assertEqual(role_of(User.objects.get(username='newstaff')), STAFF)

    def test_owner_can_add_hr(self):
        self.login('owner1')
        self.client.post(self.add_url, self.new_staff_data(role=HR))
        member = User.objects.get(username='newstaff')
        self.assertEqual(role_of(member), HR)
        self.assertTrue(member.has_perm('dashboard.manage_staff'))

    def test_hr_can_deactivate_plain_staff(self):
        self.login('hr1')
        self.client.post(self.url, {'toggle_id': self.staff.id})
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.is_active)

    def test_hr_cannot_touch_owners_or_other_hr(self):
        other_hr = User.objects.create_user('hr2', password='Pass1234!')
        set_role(other_hr, HR)
        self.login('hr1')
        self.assertEqual(self.client.post(self.url, {'toggle_id': self.owner.id}).status_code, 404)
        self.assertEqual(self.client.post(self.url, {'toggle_id': other_hr.id}).status_code, 404)

    def test_hr_cannot_change_roles(self):
        self.login('hr1')
        response = self.client.post(self.url, {'role_id': self.staff.id, 'role': HR})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(role_of(User.objects.get(pk=self.staff.pk)), STAFF)

    def test_owner_can_promote_and_demote(self):
        self.login('owner1')
        for role in [HR, OWNER, STAFF]:
            self.client.post(self.url, {'role_id': self.staff.id, 'role': role})
            self.assertEqual(role_of(User.objects.get(pk=self.staff.pk)), role)

    def test_promoted_staff_can_open_staff_accounts(self):
        self.login('owner1')
        self.client.post(self.url, {'role_id': self.staff.id, 'role': HR})
        self.client.logout()
        self.login('staff1')
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_owner_cannot_change_their_own_role(self):
        self.login('owner1')
        self.assertEqual(self.client.post(self.url, {'role_id': self.owner.id, 'role': STAFF}).status_code, 404)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_superuser)

    def test_owners_are_equal(self): #a co-owner can deactivate the first owner
        co_owner = User.objects.create_user('owner2', password='Pass1234!')
        set_role(co_owner, OWNER)
        self.login('owner2')
        self.client.post(self.url, {'toggle_id': self.owner.id})
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.is_active)

    def test_only_owners_can_reset_demo_data(self):
        category = MealCategory.objects.create(name='Rice')
        Meal.objects.create(name='Chicken Rice Box', description='Test', price_cents=500, calories=500,
                            protein_g=30, carbs_g=60, fat_g=10, image_url='', category=category)
        for username in ['hr1', 'staff1']:
            self.login(username)
            self.assertRedirects(self.client.post(reverse('dashboard:seed')), reverse('dashboard:home'))
            self.assertTrue(Meal.objects.filter(name='Chicken Rice Box').exists()) #nothing was wiped


class StaffAccountsListTests(TestCase): #filters, search and pages on Staff accounts
    def setUp(self):
        User.objects.create_user('owner1', password='Pass1234!', email='owner1@example.com', is_staff=True, is_superuser=True)
        hr = User.objects.create_user('hr1', password='Pass1234!', email='hr1@example.com')
        set_role(hr, HR)
        User.objects.create_user('staff1', password='Pass1234!', email='staff1@example.com', is_staff=True)
        User.objects.create_user('staff2', password='Pass1234!', email='kitchen@example.com', is_staff=True, is_active=False)
        self.client.login(username='owner1', password='Pass1234!')
        self.url = reverse('dashboard:staff_accounts')

    def usernames(self, **params):
        response = self.client.get(self.url, params)
        return [row['member'].username for row in response.context['rows']]

    def test_all_staff_owners_first(self):
        self.assertEqual(self.usernames(), ['owner1', 'hr1', 'staff1', 'staff2'])

    def test_role_filters(self):
        self.assertEqual(self.usernames(show=OWNER), ['owner1'])
        self.assertEqual(self.usernames(show=HR), ['hr1'])
        self.assertEqual(self.usernames(show=STAFF), ['staff1', 'staff2'])
        self.assertEqual(self.usernames(show='inactive'), ['staff2'])

    def test_search_by_username_or_email(self):
        self.assertEqual(self.usernames(q='hr'), ['hr1'])
        self.assertEqual(self.usernames(q='kitchen'), ['staff2'])

    def test_twenty_per_page(self):
        for n in range(25):
            User.objects.create_user(f'extra{n:02d}', password='Pass1234!', is_staff=True)
        self.assertEqual(len(self.usernames()), 20)
        self.assertEqual(len(self.usernames(page=2)), 9) #29 staff in total

    def test_a_button_keeps_the_filter(self):
        staff1 = User.objects.get(username='staff1')
        response = self.client.post(self.url + '?show=staff', {'toggle_id': staff1.id})
        self.assertRedirects(response, self.url + '?show=staff')


class ResetDemoDataTests(TestCase):
    def test_owner_reset_loads_the_starter_menu_and_slots(self):
        User.objects.create_user('owner1', password='Pass1234!', is_staff=True, is_superuser=True)
        self.client.login(username='owner1', password='Pass1234!')
        self.client.post(reverse('dashboard:seed'))
        self.assertEqual(Meal.objects.count(), 20)
        self.assertEqual(MenuItem.objects.count(), 20)
        self.assertEqual(PickupPoint.objects.count(), 3)
        self.assertEqual(PickupSlot.objects.count(), 30) #3 points x 5 days x lunch and dinner


class PickupPageTests(TestCase): #the revamped pickup point page
    def setUp(self):
        User.objects.create_user('staff1', password='Pass1234!', is_staff=True)
        self.client.login(username='staff1', password='Pass1234!')
        self.point = PickupPoint.objects.create(name='Library', location='Level 1')
        self.url = reverse('dashboard:pickup_detail', args=[self.point.id])
        self.monday = next_monday()
        today = timezone.localdate()
        self.busy = self.make_slot(self.monday + timedelta(days=1), time(12, 0)) #has orders
        self.empty = self.make_slot(self.monday, time(18, 0))
        self.past = self.make_slot(today - timedelta(days=7), time(12, 0))
        customer = User.objects.create_user('student1', password='Pass1234!')
        for status in ['confirmed', 'confirmed', 'cancelled']:
            Order.objects.create(user=customer, pickup_slot=self.busy, status=status, total_cents=500)

    def make_slot(self, day, start):
        return PickupSlot.objects.create(pickup_point=self.point, day=day, start_time=start,
                                         end_time=time(start.hour + 1, 0), capacity=20)

    def test_upcoming_slots_are_sorted_and_past_ones_are_separate(self):
        response = self.client.get(self.url)
        self.assertEqual(list(response.context['upcoming']), [self.empty, self.busy])
        self.assertEqual(list(response.context['past']), [self.past])

    def test_booked_leaves_out_cancelled_orders(self):
        upcoming = self.client.get(self.url).context['upcoming']
        self.assertEqual([slot.booked for slot in upcoming], [0, 2])

    def test_capacity_cannot_go_below_what_is_booked(self):
        self.client.post(self.url, {'capacity_id': self.busy.id, 'capacity': '1'})
        self.busy.refresh_from_db()
        self.assertEqual(self.busy.capacity, 20)
        self.client.post(self.url, {'capacity_id': self.busy.id, 'capacity': '25'})
        self.busy.refresh_from_db()
        self.assertEqual(self.busy.capacity, 25)

    def test_only_slots_without_orders_can_be_removed(self):
        self.client.post(self.url, {'remove_id': self.busy.id})
        self.assertTrue(PickupSlot.objects.filter(id=self.busy.id).exists())
        self.client.post(self.url, {'remove_id': self.empty.id})
        self.assertFalse(PickupSlot.objects.filter(id=self.empty.id).exists())

    def test_add_a_week_skips_slots_that_exist(self):
        data = {'add_week': '1', 'week_start': self.monday.isoformat(), 'lunch': 'on', 'dinner': 'on', 'capacity': '15'}
        self.client.post(self.url, data)
        week = PickupSlot.objects.filter(pickup_point=self.point, day__gte=self.monday,
                                         day__lte=self.monday + timedelta(days=4))
        self.assertEqual(week.count(), 10) #2 were there already, 8 were added
        self.client.post(self.url, data) #again: nothing new
        self.assertEqual(week.count(), 10)

    def test_add_a_week_needs_a_monday_and_a_time(self):
        tuesday = self.monday + timedelta(days=1)
        self.client.post(self.url, {'add_week': '1', 'week_start': tuesday.isoformat(), 'lunch': 'on', 'capacity': '15'})
        self.client.post(self.url, {'add_week': '1', 'week_start': self.monday.isoformat(), 'capacity': '15'})
        self.assertEqual(PickupSlot.objects.filter(pickup_point=self.point).count(), 3) #nothing added

    def test_same_day_and_time_twice_is_rejected(self):
        form = PickupSlotForm({'day': self.busy.day.isoformat(), 'start_time': '12:00', 'end_time': '12:30',
                               'capacity': 10}, point=self.point)
        self.assertFalse(form.is_valid())
        self.assertIn('start_time', form.errors)

    def test_edit_name_and_location(self):
        url = reverse('dashboard:pickup_edit', args=[self.point.id])
        self.client.post(url, {'name': 'Central Library', 'location': 'Main entrance', 'is_active': 'on'})
        self.point.refresh_from_db()
        self.assertEqual(self.point.name, 'Central Library')

    def test_list_counts_upcoming_slots(self):
        rows = self.client.get(reverse('dashboard:pickup_list')).context['rows']
        self.assertEqual(rows[0]['point'].upcoming, 2) #the past slot isn't counted

    def test_upcoming_slots_have_pages_of_20(self):
        for n in range(23): #23 more upcoming slots, 25 in total
            day = self.monday + timedelta(days=7 * (n // 5 + 1) + n % 5)
            self.make_slot(day, time(12, 0))
        self.assertEqual(len(self.client.get(self.url).context['upcoming']), 20)
        self.assertEqual(len(self.client.get(self.url, {'page': 2}).context['upcoming']), 5)

    def test_paging_through_past_slots_keeps_them_open(self):
        response = self.client.get(self.url, {'past_page': 1})
        self.assertTrue(response.context['show_past'])
        self.assertContains(response, '<details class="mt-3 mb-4" open>')

    def test_an_action_keeps_the_same_page(self):
        response = self.client.post(self.url + '?page=1', {'capacity_id': self.busy.id, 'capacity': '30'})
        self.assertRedirects(response, self.url + '?page=1')

    def test_pickup_points_have_pages_of_20(self):
        for n in range(24): #25 points in total
            PickupPoint.objects.create(name=f'Point {n:02d}', location='Somewhere')
        list_url = reverse('dashboard:pickup_list')
        self.assertEqual(len(self.client.get(list_url).context['rows']), 20)
        self.assertEqual(len(self.client.get(list_url, {'page': 2}).context['rows']), 5)


class ConsistencyTests(TestCase): #labels, titles and badges that should look the same everywhere
    def setUp(self):
        self.owner = User.objects.create_user('owner1', password='Pass1234!', is_staff=True, is_superuser=True)
        category = MealCategory.objects.create(name='Rice')
        self.meal = Meal.objects.create(name='Chicken Rice Box', description='Test', price_cents=500, calories=500,
                                        protein_g=30, carbs_g=60, fat_g=10, image_url='', category=category)
        self.menu = WeeklyMenu.objects.create(week_start=timezone.localdate(), order_cutoff=timezone.now())
        self.item = MenuItem.objects.create(weekly_menu=self.menu, meal=self.meal, quantity_available=10)
        point = PickupPoint.objects.create(name='Library', location='Level 1')
        self.slot = PickupSlot.objects.create(pickup_point=point, day=timezone.localdate() + timedelta(days=1),
                                              start_time=time(12, 0), end_time=time(13, 0), capacity=20)
        self.student = User.objects.create_user('student1', password='Pass1234!')

    def order(self, status):
        order = Order.objects.create(user=self.student, pickup_slot=self.slot, total_cents=500, status=status)
        OrderItem.objects.create(order=order, menu_item=self.item, quantity=1, price_at_purchase_cents=500)
        return order

    def test_staff_pages_have_their_own_tab_title(self):
        self.client.login(username='owner1', password='Pass1234!')
        self.assertContains(self.client.get(reverse('dashboard:meal_list')), '<title>Meals · CampusBox Staff</title>')

    def test_navbar_shows_the_staff_role(self):
        self.client.login(username='owner1', password='Pass1234!')
        self.assertContains(self.client.get(reverse('dashboard:home')), '>Owner</span>')
        hr = User.objects.create_user('hr1', password='Pass1234!')
        set_role(hr, HR)
        self.client.login(username='hr1', password='Pass1234!')
        self.assertContains(self.client.get(reverse('dashboard:home')), '>HR</span>')

    def test_each_status_has_its_own_badge(self):
        self.client.login(username='owner1', password='Pass1234!')
        for status, css in [('confirmed', 'bg-info-subtle'), ('ready', 'text-bg-success'), ('cancelled', 'bg-secondary-subtle')]:
            response = self.client.get(reverse('dashboard:order_detail', args=[self.order(status).id]))
            self.assertContains(response, css)

    def test_remove_is_disabled_for_a_meal_with_orders(self):
        self.order('confirmed')
        self.client.login(username='owner1', password='Pass1234!')
        response = self.client.get(reverse('dashboard:menu_detail', args=[self.menu.id]))
        self.assertContains(response, "This meal has orders, so it can't be removed.")
        self.assertNotContains(response, 'name="remove_id"')

    def test_staff_accounts_table_has_fixed_columns(self):
        self.client.login(username='owner1', password='Pass1234!')
        response = self.client.get(reverse('dashboard:staff_accounts'))
        self.assertContains(response, 'table table-fixed')
        self.assertContains(response, '<col style="width: 37%">')  #room for the role dropdown
        hr = User.objects.create_user('hr1', password='Pass1234!')
        set_role(hr, HR)
        self.client.login(username='hr1', password='Pass1234!')
        response = self.client.get(reverse('dashboard:staff_accounts'))
        self.assertContains(response, '<col style="width: 18%">')  #only one button
        self.assertNotContains(response, '{#')  #a {# #} comment only works on one line, or it shows on the page

    def test_sign_up_has_one_name(self):
        response = self.client.get(reverse('accounts:register'))
        self.assertContains(response, '<title>Sign up · CampusBox</title>')
        self.assertNotContains(response, 'Create an account')


class StaffMyAccountTests(TestCase): #staff open My account from the avatar or the sidebar
    def setUp(self):
        self.staff = User.objects.create_user('staff1', email='staff1@example.com', password='Pass1234!', is_staff=True)
        self.url = reverse('dashboard:my_account')

    def test_customers_cannot_open_it(self):
        User.objects.create_user('amy', password='Pass1234!')
        self.client.login(username='amy', password='Pass1234!')
        self.assertRedirects(self.client.get(self.url), reverse('dashboard:staff_login'), fetch_redirect_response=False)

    def test_shows_details_and_change_password_but_no_deactivate(self):
        self.client.login(username='staff1', password='Pass1234!')
        response = self.client.get(self.url)
        self.assertContains(response, '<title>My account · CampusBox Staff</title>')
        self.assertContains(response, 'staff1@example.com')
        self.assertContains(response, f'href="{reverse("accounts:change_password")}"')
        self.assertNotContains(response, f'href="{reverse("accounts:deactivate_account")}"')
        self.assertContains(response, 'Ask an owner or HR')

    def test_role_is_shown(self):
        set_role(self.staff, HR)
        self.client.login(username='staff1', password='Pass1234!')
        response = self.client.get(self.url)
        self.assertContains(response, '<dd class="col-7">HR</dd>', html=True)
        self.assertContains(response, 'Ask an owner to change')

    def test_avatar_and_sidebar_link_to_it(self):
        self.client.login(username='staff1', password='Pass1234!')
        response = self.client.get(reverse('dashboard:home'))
        self.assertContains(response, f'class="account-link d-inline-flex align-items-center gap-2" href="{self.url}"')
        self.assertContains(response, f'href="{self.url}">My account</a>')


def image_upload(name='photo.png', fmt='PNG', extra=b''):
    """A small real image as an uploaded file; extra bytes make it bigger."""
    buffer = BytesIO()
    Image.new('RGB', (30, 20), 'green').save(buffer, fmt)
    return SimpleUploadedFile(name, buffer.getvalue() + extra, content_type='image/' + fmt.lower())


TEST_MEDIA = tempfile.mkdtemp()  # uploads in these tests never touch the real media/ folder


@override_settings(MEDIA_ROOT=TEST_MEDIA)
class MealPhotoTests(TestCase): #uploading a photo on the Add and Edit meal pages
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA, ignore_errors=True)

    def setUp(self):
        User.objects.create_user('staff1', password='Pass1234!', is_staff=True)
        self.client.login(username='staff1', password='Pass1234!')
        self.category = MealCategory.objects.create(name='Rice')

    def data(self, **changes):
        data = {'name': 'Chicken Rice Box', 'description': 'Test', 'price': '6.50', 'calories': 500,
                'protein_g': 30, 'carbs_g': 60, 'fat_g': 10, 'image_url': '', 'category': self.category.id,
                'is_active': True}
        data.update(changes)
        return data

    def add(self, photo):
        return self.client.post(reverse('dashboard:meal_add'), self.data(photo=photo))

    def edit(self, meal, **changes):
        return self.client.post(reverse('dashboard:meal_edit', args=[meal.id]), self.data(**changes))

    def test_upload_is_saved_under_a_random_name(self):
        self.assertRedirects(self.add(image_upload('my cat.png')), reverse('dashboard:meal_list'))
        meal = Meal.objects.get()
        self.assertTrue(meal.photo.name.startswith('meals/') and meal.photo.name.endswith('.png'))
        self.assertNotIn('cat', meal.photo.name) #the name staff gave the file is not used
        self.assertTrue(meal.photo.storage.exists(meal.photo.name))
        self.assertEqual(meal.photo_url, meal.photo.url)

    def test_extension_follows_the_real_format(self):
        self.add(image_upload('photo.png', fmt='JPEG')) #a JPEG named .png is saved as .jpg
        self.assertTrue(Meal.objects.get().photo.name.endswith('.jpg'))

    def test_a_file_that_is_not_an_image_is_refused(self):
        self.assertEqual(self.add(SimpleUploadedFile('menu.png', b'not really a picture')).status_code, 200)
        self.assertFalse(Meal.objects.exists())

    def test_other_image_formats_are_refused(self):
        self.assertContains(self.add(image_upload('photo.gif', fmt='GIF')), 'must be a JPG, PNG or WebP image')
        self.assertFalse(Meal.objects.exists())

    def test_photo_over_the_size_limit_is_refused(self):
        big = image_upload('big.jpg', fmt='JPEG', extra=b'0' * (2 * 1024 * 1024))
        self.assertContains(self.add(big), 'at most 2 MB')
        self.assertFalse(Meal.objects.exists())

    def test_new_photo_replaces_and_deletes_the_old_file(self):
        self.add(image_upload())
        meal = Meal.objects.get()
        old = meal.photo.name
        self.edit(meal, photo=image_upload('new.png'))
        meal.refresh_from_db()
        self.assertNotEqual(meal.photo.name, old)
        self.assertFalse(meal.photo.storage.exists(old))
        self.assertTrue(meal.photo.storage.exists(meal.photo.name))

    def test_editing_without_a_new_photo_keeps_it(self):
        self.add(image_upload())
        meal = Meal.objects.get()
        old = meal.photo.name
        self.edit(meal, name='Renamed')
        meal.refresh_from_db()
        self.assertEqual(meal.photo.name, old)
        self.assertTrue(meal.photo.storage.exists(old))

    def test_removing_the_photo_falls_back_to_the_link(self):
        self.add(image_upload())
        meal = Meal.objects.get()
        old = meal.photo.name
        self.edit(meal, remove_photo='on', image_url='/static/menu/meals/chicken-rice-box.jpg')
        meal.refresh_from_db()
        self.assertFalse(meal.photo)
        self.assertFalse(meal.photo.storage.exists(old))
        self.assertEqual(meal.photo_url, '/static/menu/meals/chicken-rice-box.jpg')

    def test_missing_file_shows_the_placeholder(self):
        meal = Meal.objects.create(name='Gone', description='Test', price_cents=500, calories=500, protein_g=30,
                                   carbs_g=60, fat_g=10, category=self.category, photo='meals/deleted.png')
        self.assertTrue(meal.photo_url.endswith('menu/meal-placeholder.svg'))

    def test_deleting_a_meal_deletes_its_photo(self):
        self.add(image_upload())
        meal = Meal.objects.get()
        name = meal.photo.name
        self.client.post(reverse('dashboard:meal_delete', args=[meal.id]))
        self.assertFalse(Meal.objects.exists())
        self.assertFalse(meal.photo.storage.exists(name))


class MealListTests(TestCase): #search, filter, sort and pages on the staff Meals list
    def setUp(self):
        User.objects.create_user('staff1', password='Pass1234!', is_staff=True)
        self.client.login(username='staff1', password='Pass1234!')
        rice = MealCategory.objects.create(name='Rice')
        noodles = MealCategory.objects.create(name='Noodles')
        for name, category, price, active in [('Chicken Rice Box', rice, 650, True), ('Laksa Bowl', noodles, 720, True),
                                              ('Egg Fried Rice', rice, 520, False)]:
            Meal.objects.create(name=name, description='Test', price_cents=price, calories=500, protein_g=20,
                                carbs_g=60, fat_g=10, category=category, is_active=active)

    def names(self, **params):
        response = self.client.get(reverse('dashboard:meal_list'), params)
        return [meal.name for meal in response.context['page_obj']]

    def test_default_is_by_category_then_name(self):
        self.assertEqual(self.names(), ['Laksa Bowl', 'Chicken Rice Box', 'Egg Fried Rice'])

    def test_search_matches_name_or_category(self):
        self.assertEqual(self.names(q='laksa'), ['Laksa Bowl'])
        self.assertEqual(self.names(q='rice'), ['Chicken Rice Box', 'Egg Fried Rice']) #both names and the category

    def test_filter_by_active(self):
        self.assertEqual(self.names(show='inactive'), ['Egg Fried Rice'])
        self.assertEqual(len(self.names(show='active')), 2)

    def test_sort_by_price_both_ways_and_ignore_unknown_keys(self):
        self.assertEqual(self.names(sort='price'), ['Egg Fried Rice', 'Chicken Rice Box', 'Laksa Bowl'])
        self.assertEqual(self.names(sort='-price'), ['Laksa Bowl', 'Chicken Rice Box', 'Egg Fried Rice'])
        self.assertEqual(self.names(sort='password'), self.names()) #not in the list, so the default sort

    def test_twenty_meals_per_page(self):
        category = MealCategory.objects.get(name='Rice')
        for number in range(20):
            Meal.objects.create(name='Meal ' + str(number), description='Test', price_cents=500, calories=500,
                                protein_g=20, carbs_g=60, fat_g=10, category=category)
        self.assertEqual(len(self.names()), 20)
        self.assertEqual(len(self.names(page=2)), 3)


class MenuListTests(TestCase): #status, filters, sold totals and one query on the Weekly menus list
    def setUp(self):
        User.objects.create_user('staff1', password='Pass1234!', is_staff=True)
        self.client.login(username='staff1', password='Pass1234!')
        now, today = timezone.now(), timezone.localdate()
        monday = today - timedelta(days=today.weekday())
        self.past = WeeklyMenu.objects.create(week_start=monday - timedelta(days=21), order_cutoff=now - timedelta(days=22))
        self.current = WeeklyMenu.objects.create(week_start=monday, order_cutoff=now - timedelta(hours=1))
        self.next = WeeklyMenu.objects.create(week_start=monday + timedelta(days=7), order_cutoff=now + timedelta(days=1))
        category = MealCategory.objects.create(name='Rice')
        self.meal = Meal.objects.create(name='Chicken Rice Box', description='Test', price_cents=500, calories=500,
                                        protein_g=30, carbs_g=60, fat_g=10, category=category)

    def page(self, **params):
        return self.client.get(reverse('dashboard:menu_list'), params)

    def test_status_of_each_week(self):
        self.assertEqual((self.next.status, self.current.status, self.past.status), ('open', 'closed', 'past'))
        response = self.page()
        for label in ['Open for orders', 'Ordering closed', 'Past']:
            self.assertContains(response, label)

    def test_newest_week_first_and_filters(self):
        self.assertEqual(list(self.page().context['page_obj']), [self.next, self.current, self.past])
        self.assertEqual(list(self.page(show='upcoming').context['page_obj']), [self.next, self.current])
        self.assertEqual(list(self.page(show='past').context['page_obj']), [self.past])

    def test_sold_and_meal_counts_are_added_up(self):
        MenuItem.objects.create(weekly_menu=self.current, meal=self.meal, quantity_available=30, quantity_sold=12)
        other = Meal.objects.create(name='Laksa', description='Test', price_cents=500, calories=500, protein_g=30,
                                    carbs_g=60, fat_g=10, category=self.meal.category)
        MenuItem.objects.create(weekly_menu=self.current, meal=other, quantity_available=20, quantity_sold=5)
        menu = [m for m in self.page().context['page_obj'] if m.pk == self.current.pk][0]
        self.assertEqual((menu.meal_count, menu.sold, menu.available), (2, 17, 50))
        self.assertContains(self.page(), '17 / 50')

    def test_more_menus_do_not_mean_more_queries(self):
        with CaptureQueriesContext(connection) as three:
            self.page()
        for weeks in range(2, 6):
            menu = WeeklyMenu.objects.create(week_start=self.next.week_start + timedelta(days=7 * weeks),
                                             order_cutoff=timezone.now() + timedelta(days=7 * weeks))
            MenuItem.objects.create(weekly_menu=menu, meal=self.meal, quantity_available=10)
        with CaptureQueriesContext(connection) as seven:
            self.page()
        self.assertEqual(len(seven), len(three)) #the counts come from one annotated query, not one per row


class ResetDemoDataConfirmTests(TestCase): #Reset demo data asks before wiping anything
    def setUp(self):
        User.objects.create_user('owner1', password='Pass1234!', is_staff=True, is_superuser=True)
        self.client.login(username='owner1', password='Pass1234!')
        category = MealCategory.objects.create(name='Rice')
        Meal.objects.create(name='Keep me', description='Test', price_cents=500, calories=500,
                            protein_g=30, carbs_g=60, fat_g=10, category=category)

    def test_visiting_the_page_only_asks(self):
        self.assertContains(self.client.get(reverse('dashboard:seed')), 'Yes, reset demo data')
        self.assertTrue(Meal.objects.filter(name='Keep me').exists())

    def test_dashboard_links_to_the_confirmation_page(self):
        self.assertContains(self.client.get(reverse('dashboard:home')), f'href="{reverse("dashboard:seed")}"')


class OrderStatusBackTests(TestCase): #staff can move an order back one step after a misclick
    def setUp(self):
        User.objects.create_user('staff1', password='Pass1234!', is_staff=True)
        self.client.login(username='staff1', password='Pass1234!')
        customer = User.objects.create_user('alice', password='Pass1234!')
        point = PickupPoint.objects.create(name='Library', location='Level 1')
        slot = PickupSlot.objects.create(pickup_point=point, day=timezone.localdate() + timedelta(days=1),
                                         start_time=time(12, 0), end_time=time(13, 0), capacity=20)
        self.order = Order.objects.create(user=customer, pickup_slot=slot, total_cents=500, status='preparing')
        self.url = reverse('dashboard:order_detail', args=[self.order.id])

    def status_after(self, **data):
        self.client.post(self.url, data)
        self.order.refresh_from_db()
        return self.order.status

    def test_back_moves_one_step(self):
        self.assertEqual(self.status_after(from_status='preparing', action='back'), 'confirmed')

    def test_next_still_moves_forward(self):
        self.assertEqual(self.status_after(from_status='preparing'), 'ready')

    def test_a_stale_click_is_ignored(self):
        self.assertEqual(self.status_after(from_status='ready', action='back'), 'preparing')

    def test_confirmed_and_cancelled_have_no_back_button(self):
        for status in ['confirmed', 'cancelled']:
            Order.objects.filter(pk=self.order.pk).update(status=status)
            self.assertNotContains(self.client.get(self.url), 'value="back"')
            self.assertEqual(self.status_after(from_status=status, action='back'), status)


class InventoryTests(TestCase): #tiles that filter, search, sort, pages and one Save for the whole page
    def setUp(self):
        User.objects.create_user('staff1', password='Pass1234!', is_staff=True)
        self.client.login(username='staff1', password='Pass1234!')
        today = timezone.localdate()
        self.menu = WeeklyMenu.objects.create(week_start=today - timedelta(days=today.weekday()),
                                              order_cutoff=timezone.now() + timedelta(days=1))
        rice = MealCategory.objects.create(name='Rice')
        noodles = MealCategory.objects.create(name='Noodles')
        self.items = {}
        for name, category, available, sold in [('Chicken Rice Box', rice, 30, 30), ('Laksa Bowl', noodles, 30, 27),
                                                ('Egg Fried Rice', rice, 30, 10)]:
            meal = Meal.objects.create(name=name, description='Test', price_cents=500, calories=500, protein_g=20,
                                       carbs_g=60, fat_g=10, category=category)
            self.items[name] = MenuItem.objects.create(weekly_menu=self.menu, meal=meal,
                                                       quantity_available=available, quantity_sold=sold)
        self.url = reverse('dashboard:inventory')

    def names(self, **params):
        return [item.meal.name for item in self.client.get(self.url, params).context['page_obj']]

    def qty(self, name):
        return 'qty_' + str(self.items[name].id)

    def test_tiles_count_each_status_and_filter(self):
        tiles = self.client.get(self.url).context['tiles']
        self.assertEqual([count for value, label, count in tiles], [3, 1, 1, 1]) #all, sold out, low, in stock
        self.assertEqual(self.names(show='sold_out'), ['Chicken Rice Box'])
        self.assertEqual(self.names(show='low'), ['Laksa Bowl'])
        self.assertEqual(self.names(show='in_stock'), ['Egg Fried Rice'])

    def test_fewest_left_first_and_search(self):
        self.assertEqual(self.names(), ['Chicken Rice Box', 'Laksa Bowl', 'Egg Fried Rice'])
        self.assertEqual(self.names(sort='meal'), ['Chicken Rice Box', 'Egg Fried Rice', 'Laksa Bowl'])
        self.assertEqual(self.names(q='rice'), ['Chicken Rice Box', 'Egg Fried Rice']) #names and the Rice category

    def test_one_save_changes_every_edited_row_and_keeps_the_filter(self):
        response = self.client.post(self.url + '?show=low&q=a', {
            self.qty('Chicken Rice Box'): '40', self.qty('Laksa Bowl'): '35', self.qty('Egg Fried Rice'): '30'})
        self.assertRedirects(response, self.url + '?show=low&q=a')
        self.items['Chicken Rice Box'].refresh_from_db()
        self.items['Laksa Bowl'].refresh_from_db()
        self.assertEqual((self.items['Chicken Rice Box'].quantity_available, self.items['Laksa Bowl'].quantity_available), (40, 35))

    def test_a_bad_row_keeps_what_was_typed_and_the_good_rows_still_save(self):
        response = self.client.post(self.url, {self.qty('Laksa Bowl'): '20', self.qty('Egg Fried Rice'): '50'})
        self.assertEqual(response.status_code, 200)
        laksa = [item for item in response.context['page_obj'] if item.meal.name == 'Laksa Bowl'][0]
        self.assertEqual((laksa.typed, laksa.error), ('20', "Can't be below the 27 sold."))
        self.assertContains(response, 'Not saved: Laksa Bowl')
        self.items['Laksa Bowl'].refresh_from_db()
        self.items['Egg Fried Rice'].refresh_from_db()
        self.assertEqual((self.items['Laksa Bowl'].quantity_available, self.items['Egg Fried Rice'].quantity_available), (30, 50))

    def test_words_and_huge_numbers_are_refused(self):
        response = self.client.post(self.url, {self.qty('Egg Fried Rice'): 'ten', self.qty('Laksa Bowl'): '100000'})
        errors = {item.meal.name: item.error for item in response.context['page_obj'] if item.error}
        self.assertEqual(errors, {'Egg Fried Rice': 'Enter a whole number, 0 or more.', 'Laksa Bowl': 'Enter 9999 or less.'})

    def test_saving_with_no_changes_says_so(self):
        response = self.client.post(self.url, {self.qty('Laksa Bowl'): '30'}, follow=True)
        self.assertContains(response, 'Nothing changed, so nothing was saved.')

    def test_a_meal_from_another_week_is_404(self):
        other = WeeklyMenu.objects.create(week_start=self.menu.week_start + timedelta(days=7),
                                          order_cutoff=timezone.now() + timedelta(days=8))
        item = MenuItem.objects.create(weekly_menu=other, meal=self.items['Laksa Bowl'].meal, quantity_available=10)
        response = self.client.post(self.url, {'qty_' + str(item.id): '20'})
        self.assertEqual(response.status_code, 404)

    def test_twenty_five_meals_per_page(self):
        category = MealCategory.objects.get(name='Rice')
        for number in range(25):
            meal = Meal.objects.create(name='Meal ' + str(number), description='Test', price_cents=500, calories=500,
                                       protein_g=20, carbs_g=60, fat_g=10, category=category)
            MenuItem.objects.create(weekly_menu=self.menu, meal=meal, quantity_available=10)
        self.assertEqual(len(self.names()), 25)
        self.assertEqual(len(self.names(page=2)), 3)


class CopyLastMenuTests(TestCase): #Add weekly menu can start from the latest menu's meals and stock
    def setUp(self):
        User.objects.create_user('staff1', password='Pass1234!', is_staff=True)
        self.client.login(username='staff1', password='Pass1234!')
        today = timezone.localdate()
        monday = today - timedelta(days=today.weekday())
        self.latest = WeeklyMenu.objects.create(week_start=monday, order_cutoff=timezone.now() - timedelta(hours=1))
        category = MealCategory.objects.create(name='Rice')
        for name, active, available, sold in [('Chicken Rice Box', True, 30, 12), ('Laksa Bowl', True, 20, 20),
                                              ('Old Special', False, 10, 0)]:
            meal = Meal.objects.create(name=name, description='Test', price_cents=500, calories=500, protein_g=20,
                                       carbs_g=60, fat_g=10, category=category, is_active=active)
            MenuItem.objects.create(weekly_menu=self.latest, meal=meal, quantity_available=available, quantity_sold=sold)
        self.url = reverse('dashboard:menu_add')
        self.next_monday = monday + timedelta(days=7)
        self.data = {'week_start': self.next_monday.isoformat(),
                     'order_cutoff': (self.next_monday - timedelta(days=1)).strftime('%Y-%m-%d') + ' 23:59'}

    def test_tickbox_names_the_week_and_counts_only_switched_on_meals(self):
        response = self.client.get(self.url)
        self.assertTrue(response.context['form'].fields['copy_meals'].initial) #ticked to start with
        self.assertContains(response, 'Copy the 2 meals and their stock from the week of ' + self.latest.week_start.strftime('%a'))

    def test_copies_meals_and_stock_and_resets_sold(self):
        response = self.client.post(self.url, {**self.data, 'copy_meals': 'on'}, follow=True)
        menu = WeeklyMenu.objects.get(week_start=self.next_monday)
        self.assertRedirects(response, reverse('dashboard:menu_detail', args=[menu.id]))
        self.assertContains(response, 'Copied 2 meals from the week of')
        copied = {item.meal.name: (item.quantity_available, item.quantity_sold) for item in menu.items.select_related('meal')}
        self.assertEqual(copied, {'Chicken Rice Box': (30, 0), 'Laksa Bowl': (20, 0)}) #the switched-off meal is left out

    def test_unticked_gives_an_empty_week(self):
        self.client.post(self.url, self.data)
        self.assertEqual(WeeklyMenu.objects.get(week_start=self.next_monday).items.count(), 0)

    def test_a_refused_form_copies_nothing(self):
        bad = {**self.data, 'week_start': (self.next_monday + timedelta(days=1)).isoformat(), 'copy_meals': 'on'} #a Tuesday
        self.assertEqual(self.client.post(self.url, bad).status_code, 200)
        self.assertEqual((WeeklyMenu.objects.count(), MenuItem.objects.count()), (1, 3))

    def test_no_tickbox_when_there_is_nothing_to_copy(self):
        WeeklyMenu.objects.all().delete()
        self.assertNotIn('copy_meals', self.client.get(self.url).context['form'].fields)


class MenuDeleteTests(TestCase): #a weekly menu can be deleted from a confirm page, but only if nobody ordered from it
    def setUp(self):
        User.objects.create_user('staff1', password='Pass1234!', is_staff=True)
        self.client.login(username='staff1', password='Pass1234!')
        category = MealCategory.objects.create(name='Rice')
        self.meal = Meal.objects.create(name='Chicken Rice Box', description='Test', price_cents=500, calories=500,
                                        protein_g=30, carbs_g=60, fat_g=10, category=category)
        self.menu = WeeklyMenu.objects.create(week_start=next_monday(), order_cutoff=timezone.now() + timedelta(days=1))
        self.item = MenuItem.objects.create(weekly_menu=self.menu, meal=self.meal, quantity_available=10)
        self.url = reverse('dashboard:menu_delete', args=[self.menu.id])

    def add_order(self):
        point = PickupPoint.objects.create(name='Library', location='Level 1')
        slot = PickupSlot.objects.create(pickup_point=point, day=next_monday(), start_time=time(12, 0),
                                         end_time=time(12, 30), capacity=20)
        customer = User.objects.create_user('student1', password='Pass1234!')
        order = Order.objects.create(user=customer, pickup_slot=slot, total_cents=500)
        OrderItem.objects.create(order=order, menu_item=self.item, quantity=1, price_at_purchase_cents=500)

    def test_visiting_only_asks(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'Delete the menu for')
        self.assertContains(response, 'the 1 meal on it')
        self.assertTrue(WeeklyMenu.objects.filter(id=self.menu.id).exists())

    def test_a_week_without_orders_is_deleted_but_its_meals_stay(self):
        response = self.client.post(self.url, follow=True)
        self.assertRedirects(response, reverse('dashboard:menu_list'))
        self.assertContains(response, 'Deleted the menu for')
        self.assertFalse(WeeklyMenu.objects.filter(id=self.menu.id).exists())
        self.assertFalse(MenuItem.objects.filter(id=self.item.id).exists())
        self.assertTrue(Meal.objects.filter(id=self.meal.id).exists())

    def test_a_week_with_orders_cannot_be_deleted(self):
        self.add_order()
        detail = self.client.get(reverse('dashboard:menu_detail', args=[self.menu.id]))
        self.assertContains(detail, "This week has orders, so it can't be deleted.")
        response = self.client.post(self.url) #even a crafted POST is refused
        self.assertEqual(response.status_code, 200)
        self.assertTrue(WeeklyMenu.objects.filter(id=self.menu.id).exists())
        self.assertNotContains(response, 'class="btn btn-danger"')

    def test_a_made_up_menu_is_404(self):
        self.assertEqual(self.client.post(reverse('dashboard:menu_delete', args=[99999])).status_code, 404)
