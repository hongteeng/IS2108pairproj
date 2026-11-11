"""Prediction comes from the trained decision tree in ml/."""

from ml.services.classifier import predict_preferred_category

from .models import CustomerProfile


def get_profile(user):
    """Return the user's taste profile, or None if they haven't taken the quiz."""
    profile = CustomerProfile.objects.filter(user=user).select_related("predicted_category").first()
    if profile and profile.predicted_category is None:
        # Re-seeding deletes the categories, which clears the saved prediction.
        profile.predicted_category = predict_preferred_category(profile)
        profile.save(update_fields=["predicted_category"])
    return profile


def mark_allergens(items, profile):
    """Attach the student's allergens found in each menu item's meal, for the card badge."""
    if not profile:
        return
    allergy_ids = set(profile.allergies.values_list("id", flat=True))
    for item in items:
        item.your_allergens = [
            allergen.name for allergen in item.meal.allergens.all()
            if allergen.id in allergy_ids
        ]