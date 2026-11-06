from .cart import get_cart_lines


def cart_count(request):
    """Return the total quantity in the session cart."""
    if not request.user.is_authenticated:
        return {"cart_count": 0}
    lines, _ = get_cart_lines(request)
    return {"cart_count": sum(line["quantity"] for line in lines)}
