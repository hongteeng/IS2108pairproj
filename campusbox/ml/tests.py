from types import SimpleNamespace

from django.test import TestCase

from menu.models import MealCategory
from ml.services import classifier


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