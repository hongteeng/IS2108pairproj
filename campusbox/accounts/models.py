from django.db import models
from django.contrib.auth.models import User


class CustomerProfile(models.Model):
    """Stores dietary and meal-planning preferences for a customer."""

    GENDER_CHOICES = [
        ("female", "Female"),
        ("male", "Male"),
        ("other", "Other"),
    ]
    FITNESS_GOAL_CHOICES = [
        ("lose_weight", "Lose weight"),
        ("stay_healthy", "Stay healthy"),
        ("build_muscle", "Build muscle"),
    ]
    SPICE_TOLERANCE_CHOICES = [
        (0, "No spice"),
        (1, "Mild"),
        (2, "Medium"),
        (3, "Hot"),
    ]
    DIET_CHOICES = [
        ("none", "No Restrictions"),
        ("vegetarian", "Vegetarian"),
        ("vegan", "Vegan"),
        ("halal", "Halal"),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    age = models.IntegerField()
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
    is_on_campus = models.BooleanField(default=True)
    budget_per_meal = models.IntegerField()
    fitness_goal = models.CharField(max_length=20, choices=FITNESS_GOAL_CHOICES)
    spice_tolerance = models.IntegerField(choices=SPICE_TOLERANCE_CHOICES)
    diet = models.CharField(max_length=20, choices=DIET_CHOICES, default="none")
    allergies = models.ManyToManyField("menu.Allergen", blank=True)
    predicted_category = models.ForeignKey(
        "menu.MealCategory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    def __str__(self):
        return f"{self.user.username}'s profile"