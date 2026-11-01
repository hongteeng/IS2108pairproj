from menu.models import MenuItem


def get_cart(request):
    """Return the cart stored in the current session."""
    return request.session.get("cart", {})


def set_quantity(request, menu_item_id, quantity):
    """Set a cart item's quantity, removing it when the quantity is 0."""
    cart = get_cart(request).copy()
    menu_item_key = str(menu_item_id)
    if quantity <= 0:
        cart.pop(menu_item_key, None)
    else:
        cart[menu_item_key] = quantity
    request.session["cart"] = cart
    request.session.modified = True


def clear_cart(request):
    """Remove all items from the current session cart."""
    request.session["cart"] = {}
    request.session.modified = True


def get_cart_lines(request):
    """Return cart lines and their total in cents."""
    cart = get_cart(request)
    menu_items = MenuItem.objects.filter(
        id__in=cart.keys(),
    ).select_related("meal", "weekly_menu")
    items_by_id = {str(item.id): item for item in menu_items}
    lines = []
    total_cents = 0

    for menu_item_id, quantity in cart.items():
        menu_item = items_by_id.get(str(menu_item_id))
        if menu_item is None:
            continue
        subtotal_cents = menu_item.meal.price_cents * quantity
        lines.append({
            "menu_item": menu_item,
            "quantity": quantity,
            "price_dollars": f"{menu_item.meal.price_cents / 100:.2f}",
            "subtotal_dollars": f"{subtotal_cents / 100:.2f}",
            "stock_left": menu_item.quantity_available - menu_item.quantity_sold,
        })
        total_cents += subtotal_cents

    return lines, total_cents
