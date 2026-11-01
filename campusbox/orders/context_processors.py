from .cart import get_cart


def cart_count(request):
    """Return the total quantity in the session cart."""
    return {"cart_count": sum(get_cart(request).values())}
