from django.contrib.auth.models import User
from django.db import models


class Review(models.Model):
    """Stores a student's review of a meal."""

    RATING_CHOICES = [
        (1, "1 star"),
        (2, "2 stars"),
        (3, "3 stars"),
        (4, "4 stars"),
        (5, "5 stars"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    meal = models.ForeignKey(
        "menu.Meal",
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES)
    comment = models.TextField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
    is_hidden = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "meal"],
                name="one_review_per_user_per_meal",
            ),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.meal.name}"
