from datetime import time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from menu.models import Meal, MealCategory, MenuItem, WeeklyMenu
from orders.models import Order, PickupPoint, PickupSlot
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