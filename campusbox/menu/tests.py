from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from .models import Meal, MealCategory, MenuItem, WeeklyMenu
from .views import to_cents


class ToCentsTests(SimpleTestCase): #the Max price filter on the menu page
    def test_whole_and_decimal_dollars(self):
        self.assertEqual(to_cents('7'), 700)
        self.assertEqual(to_cents('6.5'), 650)
        self.assertEqual(to_cents('6.55'), 655)

    def test_bad_values_are_ignored(self):
        for text in ['', 'abc', '-3', 'nan', 'inf']:
            self.assertIsNone(to_cents(text))


class StockConstraintTests(TestCase): #the CheckConstraint on MenuItem
    def setUp(self):
        category = MealCategory.objects.create(name='Rice')
        meal = Meal.objects.create(name='Chicken Rice Box', description='Test', price_cents=500, calories=500,
                                   protein_g=30, carbs_g=60, fat_g=10, image_url='', category=category)
        menu = WeeklyMenu.objects.create(week_start=timezone.localdate(), order_cutoff=timezone.now())
        self.item = MenuItem.objects.create(weekly_menu=menu, meal=meal, quantity_available=5)

    def test_cannot_sell_more_than_available(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            MenuItem.objects.filter(id=self.item.id).update(quantity_sold=6)

    def test_sold_cannot_go_below_zero(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            MenuItem.objects.filter(id=self.item.id).update(quantity_sold=-1)
