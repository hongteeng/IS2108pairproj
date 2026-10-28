from django.db import models


class PickupPoint(models.Model):
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class PickupSlot(models.Model):
    pickup_point = models.ForeignKey(PickupPoint, on_delete=models.CASCADE, related_name="slots")
    day = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    capacity = models.IntegerField()

    def __str__(self):
        return self.pickup_point.name + " " + str(self.day) + " " + str(self.start_time)

