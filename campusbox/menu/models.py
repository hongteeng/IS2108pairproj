from django.db import models

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
    image_url = models.CharField(max_length=300)
    category = models.ForeignKey(MealCategory, on_delete=models.CASCADE, related_name="meals")
    #foreignkey because meal only has 1 category
    dietary_tags = models.ManyToManyField(DietaryTag, blank=True)
    #manytomany because meal can have multiple tags
    allergens = models.ManyToManyField(Allergen, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class WeeklyMenu(models.Model):
    week_start = models.DateField()
    order_cutoff = models.DateTimeField()

    def __str__(self):
        return "Week of " + str(self.week_start)


class MenuItem(models.Model): #its a meal with stockcount
    weekly_menu = models.ForeignKey(WeeklyMenu, on_delete=models.CASCADE, related_name="items")
    meal = models.ForeignKey(Meal, on_delete=models.CASCADE, related_name="menu_items")
    quantity_available = models.IntegerField()
    quantity_sold = models.IntegerField(default=0)

    def __str__(self):
        return self.meal.name + " (" + str(self.weekly_menu) + ")"

