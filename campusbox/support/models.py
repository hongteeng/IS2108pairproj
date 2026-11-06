from django.contrib.auth.models import User
from django.db import models


class SupportTicket(models.Model):
    """Stores a customer's support ticket."""

    ISSUE_TYPE_CHOICES = [
        ("missing_item", "Missing item"),
        ("wrong_item", "Wrong item"),
        ("quality", "Quality problem"),
        ("other", "Other"),
    ]
    STATUS_CHOICES = [
        ("open", "Open"),
        ("resolved", "Resolved"),
        ("rejected", "Rejected"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="tickets",
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="tickets",
    )
    issue_type = models.CharField(max_length=20, choices=ISSUE_TYPE_CHOICES)
    message = models.TextField(max_length=1000)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="open",
    )
    refund_amount_cents = models.IntegerField(default=0)
    staff_reply = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Ticket #{self.id} - {self.user.username}"
