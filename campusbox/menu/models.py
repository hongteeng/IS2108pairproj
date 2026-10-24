from django.db import models


class Meal(models.Model):
    name = models.CharField(max_length=100) #think of a class in models.py to be a sheet (table)
    description = models.CharField(max_length=300) #each field is a column
    price_cents = models.IntegerField()
    calories = models.IntegerField()
    protein_g = models.IntegerField()
    carbs_g = models.IntegerField()
    fat_g = models.IntegerField()
    image_url = models.CharField(max_length=300)
    is_available = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class PickupPoint(models.Model): #second sheet/table
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class PickupSlot(models.Model):
    pickup_point = models.ForeignKey(PickupPoint, on_delete=models.CASCADE, related_name="slots")
    label = models.CharField(max_length=50)
    capacity = models.IntegerField(default=20)

    def __str__(self):
        return self.pickup_point.name + " " + self.label