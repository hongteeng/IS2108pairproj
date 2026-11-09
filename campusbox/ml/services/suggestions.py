"""Suggest available meals from the trained association rules."""

import joblib
from django.conf import settings
from django.db.models import Case, F, IntegerField, When

from menu.models import MenuItem
from menu.utils import current_menu


MODEL_PATH = settings.BASE_DIR / "ml" / "trained_models" / "meal_suggestions.joblib"
saved = joblib.load(MODEL_PATH)
suggestions = saved["suggestions"]


def suggest_for_meals(meal_names, exclude_names=(), limit=3):
    """Return available menu items suggested for the given meals."""
    meal_names = list(meal_names)
    excluded = set(exclude_names)
    given_meals = set(meal_names)
    suggested_names = []
    for meal_name in meal_names:
        for suggested_name in suggestions.get(meal_name, []):
            if (
                suggested_name not in excluded
                and suggested_name not in given_meals
                and suggested_name not in suggested_names
            ):
                suggested_names.append(suggested_name)

    suggested_names = suggested_names[:limit]
    latest_menu = current_menu()
    if not latest_menu or not suggested_names:
        return MenuItem.objects.none()

    ordering = Case(
        *[
            When(meal__name=name, then=position)
            for position, name in enumerate(suggested_names)
        ],
        output_field=IntegerField(),
    )
    return (
        MenuItem.objects.filter(
            weekly_menu=latest_menu,
            meal__is_active=True,
            meal__name__in=suggested_names,
            quantity_sold__lt=F("quantity_available"),
        )
        .select_related("meal")
        .order_by(ordering)
    )