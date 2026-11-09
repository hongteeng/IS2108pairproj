from datetime import timedelta

from django.utils.timezone import localtime


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

    order_deadline = localtime(weekly_menu.order_cutoff).strftime(
        "%A %d %b, %I:%M %p"
    )
    order_deadline = order_deadline.replace(" 0", " ", 1)
    order_deadline = order_deadline.replace(", 0", ", ", 1)
    return menu_dates, order_deadline
