from django import template

register = template.Library()


@register.filter
def dollars(cents):
    """Format cents as a dollar amount."""
    if cents is None:
        return ""
    return f"${cents / 100:.2f}"
