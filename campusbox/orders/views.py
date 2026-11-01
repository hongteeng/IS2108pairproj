from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from menu.models import MenuItem
from . import cart


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