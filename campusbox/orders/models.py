from django.db import models
from django.contrib.auth.models import User


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


class Order(models.Model):
    """Stores a customer's meal order and pickup details."""

    STATUS_CHOICES = [
        ("confirmed", "Confirmed"),
        ("preparing", "Preparing"),
        ("ready", "Ready for pickup"),
        ("collected", "Collected"),
        ("cancelled", "Cancelled"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="orders",
    )
    pickup_slot = models.ForeignKey(
        PickupSlot,
        on_delete=models.PROTECT,
        related_name="orders",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="confirmed",
    )
    total_cents = models.IntegerField()
    payment_reference = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return f"Order #{self.id} for {self.user.username}"


class OrderItem(models.Model):
    """Stores one menu item and quantity within an order."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    menu_item = models.ForeignKey(
        "menu.MenuItem",
        on_delete=models.PROTECT,
        related_name="order_items",
    )
    quantity = models.PositiveIntegerField()
    price_at_purchase_cents = models.IntegerField()

    def __str__(self):
        return f"{self.quantity} x {self.menu_item.meal.name}"
