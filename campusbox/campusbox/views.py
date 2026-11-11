from django.db.models import F
from django.shortcuts import redirect, render

from accounts.services import get_profile, mark_allergens
from menu.models import MenuItem
from menu.utils import current_menu, menu_labels, ordering_open, with_ratings
from orders.models import Order
from orders.views import can_cancel


def index(request):
    # Staff don’t use the storefront home page.
    if request.user.is_authenticated and request.user.is_staff:
        return redirect("dashboard:home")
    menu = current_menu()
    menu_dates, order_deadline = menu_labels(menu)
    popular_meals = []
    if menu:
        popular_meals = list(
            with_ratings(MenuItem.objects.filter(
                weekly_menu=menu,
                meal__is_active=True,
                quantity_sold__lt=F("quantity_available"),
            )).select_related("meal").order_by("-quantity_sold", "meal__name")[:8]
        )
        for item in popular_meals:
            item.price_dollars = f"{item.meal.price_cents / 100:.2f}"
            item.stock_left = item.quantity_available - item.quantity_sold

    context = {
        "ordering_open": ordering_open(menu),
        "menu_dates": menu_dates,
        "order_deadline": order_deadline,
        "popular_meals": popular_meals[:4],
        "recommended_category_id": None,
    }
    if request.user.is_authenticated:
        next_order = Order.objects.filter(
            user=request.user,
            status__in=["confirmed", "preparing", "ready"],
        ).select_related("pickup_slot__pickup_point").order_by(
            "pickup_slot__day", "pickup_slot__start_time",
        ).first()
        if next_order:
            # Same cancel rule as the order page, plus that menu's cutoff for the note.
            items = list(next_order.items.select_related("menu_item__weekly_menu"))
            next_order.can_cancel = can_cancel(next_order, items)
            if items:
                next_order.cancel_deadline = menu_labels(items[0].menu_item.weekly_menu)[1]
        picked_for_you = []
        profile = get_profile(request.user)
        if profile and menu:
            picked_for_you = list(
                with_ratings(MenuItem.objects.filter(
                    weekly_menu=menu,
                    meal__is_active=True,
                    meal__category=profile.predicted_category,
                    quantity_sold__lt=F("quantity_available"),
                ).exclude(
                    meal__allergens__in=profile.allergies.all(),
                )).select_related("meal")[:4]
            )
            for item in picked_for_you:
                item.price_dollars = f"{item.meal.price_cents / 100:.2f}"
                item.stock_left = item.quantity_available - item.quantity_sold
        # Don't repeat meals that are already in Picked for you.
        picked_ids = {item.id for item in picked_for_you}
        popular_meals = [item for item in popular_meals if item.id not in picked_ids][:4]
        mark_allergens(popular_meals + picked_for_you, profile)
        context.update({
            "next_order": next_order,
            "picked_for_you": picked_for_you,
            "popular_meals": popular_meals,
            "recommended_category_id": profile.predicted_category_id if profile else None,
        })
    return render(request, 'index.html', context)