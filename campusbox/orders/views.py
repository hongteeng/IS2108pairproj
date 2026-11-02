import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from menu.models import MenuItem
from . import cart
from .models import Order, OrderItem, PickupSlot

# Tracker shows every status except "cancelled", in order.
TRACKING_STEPS = [
    choice for choice in Order.STATUS_CHOICES if choice[0] != "cancelled"
]


def can_cancel(order, items):
    """Return whether an order can still be cancelled."""
    return order.status == "confirmed" and all(
        item.menu_item.weekly_menu.order_cutoff > timezone.now()
        for item in items
    )


def get_open_slots():
    """Return upcoming slots at active pickup points, with spaces left."""
    slots = list(
        PickupSlot.objects.filter(pickup_point__is_active=True, day__gte=timezone.localdate())
        .select_related("pickup_point")
        .order_by("day", "start_time")
    )
    for slot in slots:
        # Cancelled orders free up their space.
        slot.spaces_left = slot.capacity - slot.orders.exclude(status="cancelled").count()
    return slots


def place_order(user, slot, lines, total_cents):
    """Create the order and its items, and take the meals out of stock."""
    # All or nothing: if any step fails, nothing is saved.
    with transaction.atomic():
        order = Order.objects.create(
            user=user,
            pickup_slot=slot,
            total_cents=total_cents,
            # Payment is simulated, so we generate a reference number.
            payment_reference="SIM-" + uuid.uuid4().hex[:8].upper(),
        )
        for line in lines:
            menu_item = line["menu_item"]
            OrderItem.objects.create(
                order=order,
                menu_item=menu_item,
                quantity=line["quantity"],
                price_at_purchase_cents=menu_item.meal.price_cents,
            )
            menu_item.quantity_sold += line["quantity"]
            menu_item.save()
    return order


@login_required
def checkout(request):
    """Choose a pickup slot and pay (simulated) for the cart."""
    lines, total_cents = cart.get_cart_lines(request)
    if not lines:
        messages.error(request, "Your cart is empty.")
        return redirect("orders:cart")

    slots = get_open_slots()

    if request.method == "POST":
        slot_id = request.POST.get("pickup_slot", "")
        slot = next((s for s in slots if str(s.id) == slot_id), None)
        problem = None
        if slot is None:
            problem = "Please choose a pickup slot."
        elif slot.spaces_left <= 0:
            problem = "That pickup slot is full. Please choose another."
        elif any(line["menu_item"].weekly_menu.order_cutoff < timezone.now() for line in lines):
            problem = "Ordering for this week's menu has closed."
        elif any(line["quantity"] > line["stock_left"] for line in lines):
            problem = "Some meals no longer have enough stock. Please update your cart."

        if problem:
            messages.error(request, problem)
        else:
            order = place_order(request.user, slot, lines, total_cents)
            cart.clear_cart(request)
            messages.success(request, f"Payment received. Order #{order.id} is confirmed.")
            return redirect("orders:order_detail", order_id=order.id)

    return render(request, "orders/checkout.html", {
        "lines": lines,
        "total_dollars": f"{total_cents / 100:.2f}",
        "slots": slots,
    })


@login_required
def order_detail(request, order_id):
    """Show one of the student's own orders."""
    # user=request.user means students can't open other people's orders.
    order = get_object_or_404(
        Order.objects.select_related("pickup_slot__pickup_point"),
        id=order_id,
        user=request.user,
    )
    items = order.items.select_related(
        "menu_item__meal",
        "menu_item__weekly_menu",
    )
    for item in items:
        item.subtotal_dollars = f"{item.price_at_purchase_cents * item.quantity / 100:.2f}"
    # Steps up to and including the current status are done.
    tracker = []
    if order.status != "cancelled":
        current_step = next(
            index for index, step in enumerate(TRACKING_STEPS)
            if step[0] == order.status
        )
        tracker = [
            {"label": label, "done": index <= current_step}
            for index, (_, label) in enumerate(TRACKING_STEPS)
        ]
    return render(request, "orders/order_detail.html", {
        "order": order,
        "items": items,
        "total_dollars": f"{order.total_cents / 100:.2f}",
        "tracker": tracker,
        "can_cancel": can_cancel(order, items),
    })


@login_required
def cancel_order(request, order_id):
    """Cancel the logged-in user's eligible order."""
    order = get_object_or_404(Order, id=order_id, user=request.user)
    if request.method != "POST":
        return redirect("orders:order_detail", order_id=order.id)
    
    items = order.items.select_related("menu_item__weekly_menu")
    if not can_cancel(order, items):
        messages.error(request, "This order can no longer be cancelled.")
        return redirect("orders:order_detail", order_id=order.id)

    with transaction.atomic():
        order.status = "cancelled"
        order.save(update_fields=["status"])
        for item in items:
            menu_item = item.menu_item
            menu_item.quantity_sold -= item.quantity
            menu_item.save(update_fields=["quantity_sold"])

    messages.success(
        request,
        f"Order #{order.id} cancelled. ${order.total_cents / 100:.2f} will be refunded.",
    )
    return redirect("orders:order_detail", order_id=order.id)


@login_required
def order_history(request):
    """Show the logged-in user's previous orders."""
    orders = request.user.orders.select_related(
        "pickup_slot__pickup_point",
    ).order_by("-created_at")
    for order in orders:
        order.total_dollars = f"{order.total_cents / 100:.2f}"
    return render(request, "orders/order_history.html", {"orders": orders})
    
    
@login_required
def add_to_cart(request, menu_item_id):
    """Add a meal to the cart from its detail page."""
    menu_item = get_object_or_404(MenuItem.objects.select_related("meal"), id=menu_item_id, meal__is_active=True)
    if request.method == "POST":
        quantity_text = request.POST.get("quantity", "")
        quantity = int(quantity_text) if quantity_text.isdigit() else 0
        in_cart = cart.get_cart(request).get(str(menu_item.id), 0)
        stock_left = menu_item.quantity_available - menu_item.quantity_sold
        if quantity < 1:
            messages.error(request, "Please choose at least 1.")
        elif in_cart + quantity > stock_left:
            messages.error(request, f"Only {stock_left} left, and you already have {in_cart} in your cart.")
        else:
            cart.set_quantity(request, menu_item.id, in_cart + quantity)
            messages.success(request, f"Added {quantity} x {menu_item.meal.name} to your cart.")
    return redirect("menu:meal_detail", meal_id=menu_item.meal.id)


@login_required
def cart_detail(request):
    """Show the cart with prices and the total."""
    lines, total_cents = cart.get_cart_lines(request)
    return render(request, "orders/cart.html", {
        "lines": lines,
        "total_dollars": f"{total_cents / 100:.2f}",
    })


@login_required
def update_cart(request, menu_item_id):
    """Change one cart line's quantity; 0 removes it."""
    menu_item = get_object_or_404(MenuItem, id=menu_item_id)
    if request.method == "POST":
        quantity_text = request.POST.get("quantity", "")
        stock_left = menu_item.quantity_available - menu_item.quantity_sold
        if not quantity_text.isdigit():
            messages.error(request, "Please enter a whole number.")
        elif int(quantity_text) > stock_left:
            messages.error(request, f"Only {stock_left} left.")
        else:
            cart.set_quantity(request, menu_item.id, int(quantity_text))
            messages.success(request, "Cart updated.")
    return redirect("orders:cart")