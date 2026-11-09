from django.db.models import F
from django.shortcuts import redirect, render

from accounts.models import CustomerProfile
from accounts.services import predict_preferred_category
from menu.models import MenuItem
from menu.utils import current_menu, menu_labels
from orders.models import Order


def index(request):
    # Staff don’t use the storefront home page.
    if request.user.is_authenticated and request.user.is_staff:
        return redirect("dashboard:home")
    menu = current_menu()
    menu_dates, order_deadline = menu_labels(menu)
    popular_meals = []
    if menu:
        popular_meals = list(
            MenuItem.objects.filter(
                weekly_menu=menu,
                meal__is_active=True,
                quantity_sold__lt=F("quantity_available"),
            ).select_related("meal").order_by("-quantity_sold", "meal__name")[:3]
        )
        for item in popular_meals:
            item.price_dollars = f"{item.meal.price_cents / 100:.2f}"
            item.stock_left = item.quantity_available - item.quantity_sold

    context = {
        "order_cutoff": menu.order_cutoff if menu else None,
        "menu_week_start": menu.week_start if menu else None,
        "menu_dates": menu_dates,
        "order_deadline": order_deadline,
        "popular_meals": popular_meals,
        "recommended_category_id": None,
    }
    if request.user.is_authenticated:
        next_order = Order.objects.filter(
            user=request.user,
            status__in=["confirmed", "preparing", "ready"],
        ).select_related("pickup_slot__pickup_point").order_by("-created_at").first()
        picked_for_you = []
        profile = CustomerProfile.objects.filter(
            user=request.user,
        ).select_related("predicted_category").first()
        if profile and profile.predicted_category is None:
            # Re-run the model if the category was cleared (e.g. after re-seeding).
            profile.predicted_category = predict_preferred_category(profile)
            profile.save(update_fields=["predicted_category"])
        if profile and menu:
            picked_for_you = list(
                MenuItem.objects.filter(
                    weekly_menu=menu,
                    meal__is_active=True,
                    meal__category=profile.predicted_category,
                    quantity_sold__lt=F("quantity_available"),
                ).select_related("meal")[:3]
            )
            for item in picked_for_you:
                item.price_dollars = f"{item.meal.price_cents / 100:.2f}"
                item.stock_left = item.quantity_available - item.quantity_sold
        context.update({
            "next_order": next_order,
            "picked_for_you": picked_for_you,
            "recommended_category_id": profile.predicted_category_id if profile else None,
        })
    return render(request, 'index.html', context)