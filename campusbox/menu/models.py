import uuid
from datetime import timedelta
from pathlib import Path

from django.core.validators import FileExtensionValidator
from django.db import models
from django.templatetags.static import static
from django.utils import timezone

PHOTO_TYPES = ['jpg', 'jpeg', 'png', 'webp']


def meal_photo_path(meal, filename):
    """Save an upload as meals/<random name>.<ext>, so the name staff gave the file is never used."""
    return 'meals/' + uuid.uuid4().hex + Path(filename).suffix.lower()

class MealCategory(models.Model): #different table because its something many meals share
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class DietaryTag(models.Model): 
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Allergen(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name
    
class Meal(models.Model):
    name = models.CharField(max_length=100) #think of a class in models.py to be a sheet (table)
    description = models.CharField(max_length=300) #each field is a column
    price_cents = models.IntegerField()
    calories = models.IntegerField()
    protein_g = models.IntegerField()
    carbs_g = models.IntegerField()
    fat_g = models.IntegerField()
    image_url = models.CharField(max_length=300, blank=True) #a static file or https link, used when there is no upload
    photo = models.ImageField(upload_to=meal_photo_path, blank=True, validators=[FileExtensionValidator(PHOTO_TYPES)])
    category = models.ForeignKey(MealCategory, on_delete=models.CASCADE, related_name="meals")
    #foreignkey because meal only has 1 category
    dietary_tags = models.ManyToManyField(DietaryTag, blank=True)
    #manytomany because meal can have multiple tags
    allergens = models.ManyToManyField(Allergen, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    @property
    def photo_url(self):
        """The uploaded photo if its file is there, otherwise the image link, otherwise a placeholder."""
        if self.photo and self.photo.storage.exists(self.photo.name):
            return self.photo.url
        return self.image_url or static('menu/meal-placeholder.svg')

def this_monday():
    """The Monday of the current week, so a menu that starts before it is in the past."""
    today = timezone.localdate()
    return today - timedelta(days=today.weekday())


class WeeklyMenu(models.Model):
    week_start = models.DateField()
    order_cutoff = models.DateTimeField()

    def __str__(self):
        return "Week of " + str(self.week_start)

    @property
    def status(self):
        """open (still taking orders), closed (cutoff passed, the week is being cooked) or past."""
        if timezone.now() < self.order_cutoff:
            return 'open'
        if self.week_start >= this_monday():
            return 'closed'
        return 'past'


class MenuItem(models.Model): #its a meal with stockcount
    weekly_menu = models.ForeignKey(WeeklyMenu, on_delete=models.CASCADE, related_name="items")
    meal = models.ForeignKey(Meal, on_delete=models.CASCADE, related_name="menu_items")
    quantity_available = models.IntegerField()
    quantity_sold = models.IntegerField(default=0)

    class Meta:
        constraints = [
            # The database itself refuses stock that goes below zero or above what was cooked.
            models.CheckConstraint(
                condition=models.Q(quantity_sold__gte=0, quantity_sold__lte=models.F('quantity_available')),
                name='menuitem_sold_within_available',
            ),
        ]

    @property
    def stock_left(self):
        """How many can still be ordered."""
        return self.quantity_available - self.quantity_sold

    def __str__(self):
        return self.meal.name + " (" + str(self.weekly_menu) + ")"

