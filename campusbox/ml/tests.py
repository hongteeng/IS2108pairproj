from datetime import timedelta
from types import SimpleNamespace

from django.test import TestCase
from django.utils import timezone

from menu.models import Meal, MealCategory, MenuItem, WeeklyMenu
from ml.services import classifier
from ml.services.suggestions import suggest_for_meals


def make_profile(**changes): #a fake student profile, the classifier only reads these 7 attributes
    data = {
        'age': 21, 'gender': 'female', 'is_on_campus': True, 'budget_per_meal': 8,
        'fitness_goal': 'stay_healthy', 'spice_tolerance': 1, 'diet': 'none',
    }
    data.update(changes)
    return SimpleNamespace(**data)


class ClassifierTests(TestCase):
    def setUp(self): #the model predicts category names, so the fake database needs a category for each one
        for name in classifier.model.classes_:
            MealCategory.objects.create(name=name)

    def test_returns_a_meal_category(self):
        result = classifier.predict_preferred_category(make_profile())
        self.assertIsInstance(result, MealCategory)
        self.assertIn(result.name, list(classifier.model.classes_))

    def test_every_answer_from_the_quiz_works(self):
        for diet in ['none', 'vegetarian', 'vegan', 'halal']:
            for goal in ['lose_weight', 'stay_healthy', 'build_muscle']:
                for gender in ['female', 'male', 'other']:
                    profile = make_profile(diet=diet, fitness_goal=goal, gender=gender)
                    self.assertIsNotNone(classifier.predict_preferred_category(profile))

    def test_same_profile_gets_the_same_answer(self):
        first = classifier.predict_preferred_category(make_profile())
        second = classifier.predict_preferred_category(make_profile())
        self.assertEqual(first, second)

    def test_returns_none_if_the_category_is_not_in_the_database(self):
        MealCategory.objects.all().delete() #what happens after a re-seed wipes the categories
        self.assertIsNone(classifier.predict_preferred_category(make_profile()))


class SuggestionTests(TestCase):
    def setUp(self):
        category = MealCategory.objects.create(name='Mixed')
        menu = WeeklyMenu.objects.create(
            week_start=timezone.localdate() + timedelta(days=7),
            order_cutoff=timezone.now() + timedelta(days=1), #the current menu
        )
        #each of these is the saved suggestion for one meal in the cart below
        for name in ['Egg Mayo Sandwich Set', 'Teriyaki Salmon Bowl', 'Greek Chicken Salad', 'Tuna Mayo Onigiri Set']:
            meal = Meal.objects.create(name=name, description='Test', price_cents=500, calories=500,
                                       protein_g=20, carbs_g=50, fat_g=10, image_url='', category=category)
            sold = 5 if name == 'Egg Mayo Sandwich Set' else 0 #this one is sold out
            MenuItem.objects.create(weekly_menu=menu, meal=meal, quantity_available=5, quantity_sold=sold)

    def test_sold_out_suggestion_is_replaced_by_the_next_one(self):
        cart = ['Chicken Rice Box', 'Salmon Poke Bowl', 'Protein Pasta', 'Laksa Noodle Bowl']
        names = [item.meal.name for item in suggest_for_meals(cart)]
        self.assertEqual(names, ['Teriyaki Salmon Bowl', 'Greek Chicken Salad', 'Tuna Mayo Onigiri Set'])
