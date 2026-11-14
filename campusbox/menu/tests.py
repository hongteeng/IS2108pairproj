from django.test import SimpleTestCase

from .views import to_cents


class ToCentsTests(SimpleTestCase): #the Max price filter on the menu page
    def test_whole_and_decimal_dollars(self):
        self.assertEqual(to_cents('7'), 700)
        self.assertEqual(to_cents('6.5'), 650)
        self.assertEqual(to_cents('6.55'), 655)

    def test_bad_values_are_ignored(self):
        for text in ['', 'abc', '-3', 'nan', 'inf']:
            self.assertIsNone(to_cents(text))
