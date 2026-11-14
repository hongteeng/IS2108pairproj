from datetime import time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
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
        self.assertRedirects(self.client.post(reverse('dashboard:menu_add'), data), reverse('dashboard:menu_list'))


class CraftedPostTests(TestCase): #a POST with a made-up id should give "not found", not crash the page
    def setUp(self):
        User.objects.create_user('staff1', password='Pass1234!', is_staff=True)
        self.client.login(username='staff1', password='Pass1234!')
        self.menu = WeeklyMenu.objects.create(week_start=timezone.localdate(), order_cutoff=timezone.now())
        self.point = PickupPoint.objects.create(name='Library', location='Level 1')

    def test_inventory_with_bad_item_id_is_404(self):
        response = self.client.post(reverse('dashboard:inventory'), {'item_id': 'abc', 'quantity': '5'})
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
