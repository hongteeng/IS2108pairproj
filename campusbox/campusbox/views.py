from django.db.models import F
from django.shortcuts import render

from accounts.models import CustomerProfile
from menu.models import MenuItem, WeeklyMenu
from orders.models import Order


def index(request):
    menu = WeeklyMenu.objects.order_by("-week_start").first()
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

    context = {
        "order_cutoff": menu.order_cutoff if menu else None,
        "popular_meals": popular_meals,
    }
    if request.user.is_authenticated and not request.user.is_staff:
        next_order = Order.objects.filter(
            user=request.user,
            status__in=["confirmed", "preparing", "ready"],
        ).select_related("pickup_slot__pickup_point").order_by("-created_at").first()
        picked_for_you = []
        profile = CustomerProfile.objects.filter(
            user=request.user,
            predicted_category__isnull=False,
        ).select_related("predicted_category").first()
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
        context.update({
            "next_order": next_order,
            "picked_for_you": picked_for_you,
        })
    return render(request, 'index.html', context)