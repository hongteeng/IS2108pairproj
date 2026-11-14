from datetime import time, timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from menu.models import Meal, MealCategory, MenuItem, WeeklyMenu
from orders.models import Order, OrderItem, PickupPoint, PickupSlot
from orders.views import OutOfStock, SlotFull, place_order


class PlaceOrderTests(TestCase):
    def setUp(self): #runs before every test, builds a small fake database
        category = MealCategory.objects.create(name='Rice')
        meal = Meal.objects.create(
            name='Chicken Rice Box', description='Test', price_cents=500,
            calories=500, protein_g=30, carbs_g=60, fat_g=10,
            image_url='', category=category,
        )
        menu = WeeklyMenu.objects.create(week_start=timezone.localdate(), order_cutoff=timezone.now())
        self.item = MenuItem.objects.create(weekly_menu=menu, meal=meal, quantity_available=5)
        point = PickupPoint.objects.create(name='Library', location='Level 1')
        self.slot = PickupSlot.objects.create(
            pickup_point=point, day=timezone.localdate() + timedelta(days=1),
            start_time=time(12, 0), end_time=time(12, 30), capacity=1,
        )
        self.alice = User.objects.create_user('alice', password='Pass1234!')
        self.bob = User.objects.create_user('bob', password='Pass1234!')

    def lines(self, quantity):
        return [{'menu_item': self.item, 'quantity': quantity}]

    def test_full_slot_is_refused(self):
        place_order(self.alice, self.slot, self.lines(1), 500)
        with self.assertRaises(SlotFull):
            place_order(self.bob, self.slot, self.lines(1), 500)
        self.assertEqual(Order.objects.count(), 1)

    def test_full_slot_leaves_stock_alone(self):
        place_order(self.alice, self.slot, self.lines(1), 500)
        with self.assertRaises(SlotFull):
            place_order(self.bob, self.slot, self.lines(2), 1000)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity_sold, 1) #only Alice's meal was counted

    def test_cancelled_order_frees_its_place(self):
        order = place_order(self.alice, self.slot, self.lines(1), 500)
        order.status = 'cancelled'
        order.save()
        place_order(self.bob, self.slot, self.lines(1), 500) #no error: the place is free again
        self.assertEqual(Order.objects.count(), 2)

    def test_too_little_stock_undoes_the_order(self):
        with self.assertRaises(OutOfStock):
            place_order(self.alice, self.slot, self.lines(6), 3000) #only 5 available
        self.assertEqual(Order.objects.count(), 0)


class CancelOrderTests(TestCase):
    def setUp(self):
        category = MealCategory.objects.create(name='Rice')
        meal = Meal.objects.create(
            name='Chicken Rice Box', description='Test', price_cents=500,
            calories=500, protein_g=30, carbs_g=60, fat_g=10,
            image_url='', category=category,
        )
        menu = WeeklyMenu.objects.create(
            week_start=timezone.localdate() + timedelta(days=7),
            order_cutoff=timezone.now() + timedelta(days=1), #still before the cutoff, so it can be cancelled
        )
        self.item = MenuItem.objects.create(weekly_menu=menu, meal=meal, quantity_available=5, quantity_sold=2)
        point = PickupPoint.objects.create(name='Library', location='Level 1')
        slot = PickupSlot.objects.create(
            pickup_point=point, day=timezone.localdate() + timedelta(days=8),
            start_time=time(12, 0), end_time=time(12, 30), capacity=20,
        )
        user = User.objects.create_user('alice', password='Pass1234!')
        self.order = Order.objects.create(user=user, pickup_slot=slot, total_cents=1000)
        OrderItem.objects.create(order=self.order, menu_item=self.item, quantity=2, price_at_purchase_cents=500)
        self.client.login(username='alice', password='Pass1234!')
        self.url = reverse('orders:cancel_order', args=[self.order.id])

    def test_cancelling_returns_the_stock(self):
        self.client.post(self.url)
        self.order.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(self.order.status, 'cancelled')
        self.assertEqual(self.item.quantity_sold, 0)

    def test_a_second_cancel_does_not_return_the_stock_again(self):
        self.client.post(self.url)
        # Pretend the second click passed the first check before the first click finished (a double click).
        with mock.patch('orders.views.can_cancel', return_value=True):
            response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity_sold, 0) #not -2
