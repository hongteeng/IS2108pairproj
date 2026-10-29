from menu.models import MealCategory


def predict_preferred_category(profile) -> MealCategory | None:
    """Temporary rule-based placeholder until the ML model is ready."""
    if profile.diet in {"vegetarian", "vegan"}:
        category_name = "Vegetarian"
    elif profile.fitness_goal == "build_muscle":
        category_name = "High-Protein"
    elif profile.fitness_goal == "lose_weight":
        category_name = "Low-Carb"
    else:
        category_name = "Asian Rice Bowls"

    return MealCategory.objects.filter(name=category_name).first()
