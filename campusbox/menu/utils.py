from datetime import timedelta

from django.utils import timezone
from django.utils.timezone import localtime

from .models import WeeklyMenu


def current_menu():
    """Return the menu students should currently use."""
    # Prefer the earliest future cutoff so a new future menu doesn’t replace the one students are ordering from.
    return (
        WeeklyMenu.objects.filter(order_cutoff__gt=timezone.now())
        .order_by("week_start")
        .first()
        or WeeklyMenu.objects.order_by("-week_start").first()
    )


def menu_labels(weekly_menu):
    """Return the menu date range and local order deadline."""
    if weekly_menu is None:
        return "", ""

    start = weekly_menu.week_start
    end = start + timedelta(days=4)
    start_day = start.strftime("%d").lstrip("0")
    end_day = end.strftime("%d").lstrip("0")
    if start.month == end.month:
        menu_dates = f"{start_day}–{end_day} {end.strftime('%b')}"
    else:
        menu_dates = f"{start_day} {start.strftime('%b')} – {end_day} {end.strftime('%b')}"

    cutoff = localtime(weekly_menu.order_cutoff)
    order_deadline = f"{cutoff:%A} {cutoff.day} {cutoff:%b, %H:%M}"
    return menu_dates, order_deadline


def ordering_open(weekly_menu):
    """Return whether students can still order from this menu."""
    return weekly_menu is not None and weekly_menu.order_cutoff > timezone.now()
