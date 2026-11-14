from django.contrib.auth import authenticate, login as auth_login
from django.contrib import messages
from django.contrib.auth.models import User
from django.http import Http404
from django.core.paginator import Paginator
from django.db.models import Count, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from datetime import date, datetime, time, timedelta
from accounts.models import CustomerProfile
from accounts.forms import LoginForm
from django.db import transaction
from django.db.models import ProtectedError
from menu.models import Meal, WeeklyMenu, MenuItem, this_monday
from menu.utils import current_menu, menu_labels
from orders.models import Order, OrderItem, PickupPoint, PickupSlot
from support.models import SupportTicket
from .forms import MealForm, NewWeeklyMenuForm, WeeklyMenuForm, week_label, MenuItemForm, PickupPointForm, PickupSlotForm, SlotWeekForm, StaffAccountForm
from .roles import HR, OWNER, ROLE_CHOICES, ROLE_NAMES, STAFF, can_manage, role_of, set_role


def posted_id(request, field): #an id typed into a form arrives as text, so refuse anything that is not a number
    value = request.POST.get(field, '')
    if not value.isdigit():
        raise Http404
    return int(value)

def staff_login(request): #function to authenticate user, runs when visiting /dashboard/login
    error = None
    if request.method == 'POST': #post vs GET. POST means clicking on login button. GET means view, clicking on link going to website
        form = LoginForm(request.POST)
        if form.is_valid():
            user = authenticate(
                request,
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password'],
            )
            # Same message for every failure so the page doesn’t reveal which accounts exist.
            if user is None or not user.is_staff:
                error = 'Incorrect username or password.'
            else:
                auth_login(request, user)
                return redirect('dashboard:home') #send them to the dashboard
    else:
        form = LoginForm()
    return render(request, 'dashboard/staff_login.html', {'form': form, 'error': error})

def home(request):
    menu = current_menu()
    to_prepare = Order.objects.filter(
        status__in=["confirmed", "preparing"],
    ).count()
    ready_count = Order.objects.filter(status="ready").count()
    open_tickets = SupportTicket.objects.filter(status="open").count()
    sold_out = 0
    low_stock = 0
    if menu:
        stock_items = MenuItem.objects.filter(weekly_menu=menu).annotate(
            stock_remaining=F("quantity_available") - F("quantity_sold"),
        )
        sold_out = stock_items.filter(stock_remaining__lte=0).count()
        low_stock = stock_items.filter(
            stock_remaining__gte=1,
            stock_remaining__lte=LOW_STOCK,
        ).count()

    week_start = timezone.now() - timedelta(days=7)
    week_orders = Order.objects.filter(
        created_at__gte=week_start,
    ).exclude(status="cancelled")
    week_summary = week_orders.aggregate(
        count=Count("id"),
        revenue=Coalesce(Sum("total_cents"), Value(0)),
    )
    top_meals = OrderItem.objects.filter(
        order__in=week_orders,
    ).values(
        "menu_item__meal__name",
    ).annotate(
        total=Sum("quantity"),
    ).order_by("-total")[:3]

    # Taste-quiz predictions from the ML model, used to plan next week’s menu.
    predicted_profiles = CustomerProfile.objects.filter(
        predicted_category__isnull=False,
    ).values(
        name=F("predicted_category__name"),
    ).annotate(
        count=Count("id"),
    ).order_by("-count")
    demand_total = sum(group["count"] for group in predicted_profiles)
    demand = [
        {
            "name": group["name"],
            "count": group["count"],
            "percent": round(group["count"] * 100 / demand_total) if demand_total else 0,
        }
        for group in predicted_profiles
    ]

    return render(request, "dashboard/home.html", {
        "to_prepare": to_prepare,
        "ready_count": ready_count,
        "open_tickets": open_tickets,
        "sold_out": sold_out,
        "low_stock": low_stock,
        "week_orders": week_summary["count"],
        "week_revenue_cents": week_summary["revenue"],
        "top_meals": top_meals,
        "demand": demand,
        "demand_total": demand_total,
    })

MEAL_FILTERS = [('', 'All'), ('active', 'Active'), ('inactive', 'Inactive')]

MEAL_SORTS = {
    'name': ['name'],
    'category': ['category__name', 'name'],
    'price': ['price_cents'],
    'calories': ['calories'],
}


def meal_list(request): #search, filter, sort and pages, the same way as the Orders list
    show = request.GET.get('show', '')
    q = request.GET.get('q', '').strip()
    meals = Meal.objects.select_related('category')
    if show == 'active':
        meals = meals.filter(is_active=True)
    elif show == 'inactive':
        meals = meals.filter(is_active=False)
    if q:
        meals = meals.filter(Q(name__icontains=q) | Q(category__name__icontains=q))

    # ?sort=price is low to high, ?sort=-price is high to low. Only the keys above are allowed.
    sort = request.GET.get('sort', 'category')
    key = sort.lstrip('-')
    if key not in MEAL_SORTS:
        sort, key = 'category', 'category'
    direction = '-' if sort.startswith('-') else ''
    sort = direction + key
    meals = meals.order_by(*[direction + field for field in MEAL_SORTS[key]], 'id')  # id keeps ties in a fixed order

    page_obj = Paginator(meals, 20).get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)  # page links add their own page number
    querystring = params.urlencode()
    params.pop('sort', None)  # sort links add their own sort
    return render(request, 'dashboard/meal_list.html', {
        'page_obj': page_obj,
        'querystring': querystring,
        'sort_querystring': params.urlencode(),
        'sort': sort,
        'show': show,
        'q': q,
        'filters': MEAL_FILTERS,
    })


def delete_photo_file(photo):
    """Delete an uploaded photo's file, so replaced and removed photos don't pile up in media/."""
    if photo:
        photo.storage.delete(photo.name)


def meal_edit(request, meal_id):
    meal = get_object_or_404(Meal, pk=meal_id)
    old_photo, current_photo = meal.photo.name, meal.photo_url  # read before the form changes the meal
    if request.method == 'POST':
        form = MealForm(request.POST, request.FILES, instance=meal)  # request.FILES holds the uploaded photo
        if form.is_valid():
            form.save()  # updates this meal because the form was given instance=meal
            if old_photo and old_photo != meal.photo.name:  # replaced or removed
                meal.photo.storage.delete(old_photo)
            return redirect('dashboard:meal_list')
    else:
        form = MealForm(instance=meal)
    return render(request, 'dashboard/meal_form.html', {
        'form': form, 'title': 'Edit meal', 'current_photo': current_photo, 'has_upload': bool(old_photo),
    })


def meal_add(request):
    if request.method == 'POST':
        form = MealForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()  # saves the meal, its dietary tags and allergens
            return redirect('dashboard:meal_list')
    else:
        form = MealForm()
    return render(request, 'dashboard/meal_form.html', {'form': form, 'title': 'Add meal'})


def meal_delete(request, meal_id):
    meal = get_object_or_404(Meal, pk=meal_id)
    error = None
    if request.method == 'POST':
        try:
            photo = meal.photo
            meal.delete()
            delete_photo_file(photo)  # only once the meal is really gone
            return redirect('dashboard:meal_list')
        except ProtectedError:
            error = 'This meal has orders, so it cannot be deleted. Edit it and switch off "Show on the storefront" instead.'
    return render(request, 'dashboard/meal_confirm_delete.html', {'meal': meal, 'error': error})


MENU_FILTERS = [('', 'All'), ('upcoming', 'This week and later'), ('past', 'Past')]


def menu_list(request): #newest week first, with each week's status and how much of it sold
    show = request.GET.get('show', '')
    # One query for the whole page: the counts are added up by the database, not once per row
    menus = WeeklyMenu.objects.annotate(
        meal_count=Count('items'),
        sold=Coalesce(Sum('items__quantity_sold'), 0),
        available=Coalesce(Sum('items__quantity_available'), 0),
    ).order_by('-week_start')
    if show == 'upcoming':
        menus = menus.filter(week_start__gte=this_monday())
    elif show == 'past':
        menus = menus.filter(week_start__lt=this_monday())

    page_obj = Paginator(menus, 20).get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)  # page links add their own page number
    return render(request, 'dashboard/menu_list.html', {
        'page_obj': page_obj,
        'querystring': params.urlencode(),
        'show': show,
        'filters': MENU_FILTERS,
    })


def copy_meals(source, menu):
    """Put the source menu's meals and stock on a new menu. Sold starts at 0; switched-off meals are left out."""
    items = source.items.filter(meal__is_active=True)
    MenuItem.objects.bulk_create([
        MenuItem(weekly_menu=menu, meal_id=item.meal_id, quantity_available=item.quantity_available, quantity_sold=0)
        for item in items
    ])
    return len(items)


def menu_add(request):
    if request.method == 'POST':
        form = NewWeeklyMenuForm(request.POST)
        if form.is_valid():
            with transaction.atomic():  # the menu and its copied meals are saved together, or not at all
                menu = form.save()
                copied = copy_meals(form.source, menu) if form.cleaned_data.get('copy_meals') else 0
            if copied:
                messages.success(request, 'Copied ' + str(copied) + ' meal' + ('s' if copied != 1 else '')
                                 + ' from the week of ' + week_label(form.source.week_start)
                                 + '. Change their stock or remove meals below.')
            else:
                messages.success(request, 'Weekly menu added. Add its meals below.')
            return redirect('dashboard:menu_detail', menu_id=menu.id)  # straight to the new week, to check its meals
    else:
        today = timezone.localdate()
        next_monday = today + timedelta(days=7 - today.weekday()) #the next week that has not started yet
        form = NewWeeklyMenuForm(initial={
            'week_start': next_monday,
            'order_cutoff': datetime.combine(next_monday - timedelta(days=1), time(23, 59)), #Sunday 23:59, the night before
        })
    return render(request, 'dashboard/menu_form.html', {'form': form, 'title': 'Add weekly menu'})


def menu_edit(request, menu_id):
    menu = get_object_or_404(WeeklyMenu, pk=menu_id)
    if request.method == 'POST':
        form = WeeklyMenuForm(request.POST, instance=menu)
        if form.is_valid():
            form.save()
            return redirect('dashboard:menu_detail', menu_id=menu.id)
    else:
        form = WeeklyMenuForm(instance=menu)
    return render(request, 'dashboard/menu_form.html', {'form': form, 'title': 'Edit weekly menu', 'menu': menu})


def menu_detail(request, menu_id):
    menu = get_object_or_404(WeeklyMenu, pk=menu_id)
    error = None
    form = MenuItemForm()

    if request.method == 'POST':
        if 'remove_id' in request.POST:
            item = get_object_or_404(MenuItem, pk=posted_id(request, 'remove_id'), weekly_menu=menu) #only items on this menu
            try:
                item.delete()
            except ProtectedError:
                error = 'This meal already has orders, so it cannot be removed.'
        else:
            form = MenuItemForm(request.POST)
            if form.is_valid():
                meal = form.cleaned_data['meal']
                if MenuItem.objects.filter(weekly_menu=menu, meal=meal).exists():
                    error = 'That meal is already on this menu.'
                else:
                    item = MenuItem(
                        weekly_menu=menu,
                        meal=meal,
                        quantity_available=form.cleaned_data['quantity_available'],
                        quantity_sold=0,
                    )
                    item.save()
                    form = MenuItemForm()

    items = menu.items.select_related('meal').annotate(order_total=Count('order_items')) #Remove only without orders
    menu_dates, order_deadline = menu_labels(menu)
    return render(request, 'dashboard/menu_detail.html', {
        'menu': menu,
        'menu_dates': menu_dates,
        'order_deadline': order_deadline,
        'items': items,
        'has_orders': any(item.order_total for item in items),  # Delete menu only while nobody has ordered from it
        'form': form,
        'error': error,
    })

def menu_delete(request, menu_id): #visiting only asks; the POST from that page deletes, and only a week nobody ordered from
    menu = get_object_or_404(WeeklyMenu, pk=menu_id)
    menu_dates = menu_labels(menu)[0]
    has_orders = OrderItem.objects.filter(menu_item__weekly_menu=menu).exists()
    if request.method == 'POST' and not has_orders:
        try:
            menu.delete()  # its meals on the menu go with it; the meals themselves stay in Meals
        except ProtectedError:
            has_orders = True  # an order came in after the page loaded; the database refused, nothing was deleted
        else:
            messages.success(request, 'Deleted the menu for ' + menu_dates + '.')
            return redirect('dashboard:menu_list')
    return render(request, 'dashboard/menu_confirm_delete.html', {
        'menu': menu,
        'menu_dates': menu_dates,
        'meal_count': menu.items.count(),
        'has_orders': has_orders,
    })


def booked_counts(slots):
    """Add booked (orders that aren't cancelled) and order_total (every order, cancelled too) to each slot."""
    return slots.annotate(
        booked=Count('orders', filter=~Q(orders__status='cancelled')),
        order_total=Count('orders'),
    )


def pickup_list(request):
    today = timezone.localdate()
    menu = current_menu()
    points = PickupPoint.objects.annotate(
        upcoming=Count('slots', filter=Q(slots__day__gte=today)),
    ).order_by('-is_active', 'name')
    page_obj = Paginator(points, 20).get_page(request.GET.get('page'))
    rows = []
    for point in page_obj: #only work out bookings for the points on this page
        week = None
        if menu: #how full this point is in the current menu's week
            week_slots = booked_counts(point.slots.filter(
                day__range=(menu.week_start, menu.week_start + timedelta(days=4))))
            capacity = sum(slot.capacity for slot in week_slots)
            booked = sum(slot.booked for slot in week_slots)
            week = {'booked': booked, 'capacity': capacity,
                    'percent': round(booked * 100 / capacity) if capacity else 0}
        rows.append({'point': point, 'week': week})
    params = request.GET.copy()
    params.pop('page', None) #page links add their own page number
    return render(request, 'dashboard/pickup_list.html', {
        'rows': rows,
        'page_obj': page_obj,
        'querystring': params.urlencode(),
        'menu_dates': menu_labels(menu)[0],
    })


def pickup_add(request):
    if request.method == 'POST':
        form = PickupPointForm(request.POST)
        if form.is_valid():
            point = form.save()
            return redirect('dashboard:pickup_detail', point_id=point.id)
    else:
        form = PickupPointForm()
    return render(request, 'dashboard/pickup_form.html', {'form': form, 'title': 'Add pickup point'})


def pickup_edit(request, point_id):
    point = get_object_or_404(PickupPoint, pk=point_id)
    form = PickupPointForm(request.POST or None, instance=point)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, point.name + ' saved.')
        return redirect('dashboard:pickup_detail', point_id=point.id)
    return render(request, 'dashboard/pickup_form.html', {'form': form, 'title': 'Edit pickup point', 'point': point})


def pickup_detail(request, point_id):
    point = get_object_or_404(PickupPoint, pk=point_id)
    error = None
    form = PickupSlotForm(point=point)
    today = timezone.localdate()
    next_monday = today + timedelta(days=7 - today.weekday())
    week_form = SlotWeekForm(initial={'week_start': next_monday})

    if request.method == 'POST':
        if 'toggle' in request.POST: #open or close the whole point
            point.is_active = not point.is_active
            point.save()
            messages.success(request, point.name + (' is open again.' if point.is_active else ' is closed.'))
            return redirect(request.get_full_path()) #same page of slots
        elif 'remove_id' in request.POST:
            slot = get_object_or_404(PickupSlot, pk=posted_id(request, 'remove_id'), pickup_point=point) #only this point's slots
            try:
                slot.delete()
                messages.success(request, 'Slot removed.')
                return redirect(request.get_full_path()) #same page of slots
            except ProtectedError:
                error = 'This slot already has orders, so it cannot be removed.'
        elif 'capacity_id' in request.POST: #change one slot's capacity
            slot = booked_counts(point.slots).filter(pk=posted_id(request, 'capacity_id')).first()
            if slot is None:
                raise Http404
            capacity = request.POST.get('capacity', '')
            if capacity.isdigit() and int(capacity) >= max(slot.booked, 1):
                slot.capacity = int(capacity)
                slot.save(update_fields=['capacity'])
                messages.success(request, 'Capacity set to ' + capacity + '.')
                return redirect(request.get_full_path()) #same page of slots
            error = 'Capacity must be a whole number, at least 1 and at least the ' + str(slot.booked) + ' already booked.'
        elif 'add_week' in request.POST: #Monday to Friday in one go
            week_form = SlotWeekForm(request.POST)
            if week_form.is_valid():
                slots, skipped = week_form.new_slots(point)
                PickupSlot.objects.bulk_create(slots)
                note = ' (' + str(skipped) + ' already existed)' if skipped else ''
                messages.success(request, 'Added ' + str(len(slots)) + ' slots' + note + '.')
                return redirect(request.get_full_path()) #same page of slots
        else: #one slot
            form = PickupSlotForm(request.POST, point=point)
            if form.is_valid():  # the form checks the day, the times and duplicates
                slot = form.save(commit=False)
                slot.pickup_point = point
                slot.save()
                messages.success(request, 'Slot added.')
                return redirect(request.get_full_path()) #same page of slots

    slots = booked_counts(point.slots)
    upcoming = Paginator(slots.filter(day__gte=today).order_by('day', 'start_time'), 20).get_page(request.GET.get('page'))
    past = Paginator(slots.filter(day__lt=today).order_by('-day', 'start_time'), 20).get_page(request.GET.get('past_page'))
    upcoming_params = request.GET.copy()
    upcoming_params.pop('page', None) #each list's links add their own page number
    past_params = request.GET.copy()
    past_params.pop('past_page', None)
    return render(request, 'dashboard/pickup_detail.html', {
        'point': point,
        'upcoming': upcoming,
        'past': past,
        'upcoming_querystring': upcoming_params.urlencode(),
        'past_querystring': past_params.urlencode(),
        'show_past': 'past_page' in request.GET, #keep Past slots open while paging through it
        'form': form,
        'week_form': week_form,
        'error': error,
    })

ORDER_FILTERS = [
    ('', 'All'),
    ('to_prepare', 'To prepare'),
    ('ready', 'Ready for pickup'),
    ('collected', 'Collected'),
    ('cancelled', 'Cancelled'),
]


ORDER_SORTS = {
    'order': ['id'],
    'customer': ['user__username'],
    'pickup': ['pickup_slot__day', 'pickup_slot__start_time'],
    'total': ['total_cents'],
}


def order_list(request):
    status = request.GET.get('status', '')
    q = request.GET.get('q', '').strip()
    orders = Order.objects.select_related(
        'user',
        'pickup_slot__pickup_point',
    )
    if status == 'to_prepare':
        orders = orders.filter(status__in=['confirmed', 'preparing'])
    elif status in ('ready', 'collected', 'cancelled'):
        orders = orders.filter(status=status)
    if q:
        # "12" or "#12" finds order 12; any text also matches usernames
        number = q.lstrip('#')
        match = Q(user__username__icontains=q)
        if number.isdigit():
            match |= Q(id=number)
        orders = orders.filter(match)

    # ?sort=total is low to high, ?sort=-total is high to low. Only the keys above are allowed.
    sort = request.GET.get('sort', '-order')
    key = sort.lstrip('-')
    if key not in ORDER_SORTS:
        sort, key = '-order', 'order'
    direction = '-' if sort.startswith('-') else ''
    sort = direction + key
    fields = [direction + field for field in ORDER_SORTS[key]]
    orders = orders.order_by(*fields, 'id')  # id keeps ties in a fixed order

    page_obj = Paginator(orders, 20).get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)  # page links add their own page number
    querystring = params.urlencode()
    params.pop('sort', None)  # sort links add their own sort
    return render(request, 'dashboard/order_list.html', {
        'page_obj': page_obj,
        'querystring': querystring,
        'sort_querystring': params.urlencode(),
        'sort': sort,
        'status': status,
        'q': q,
        'filters': ORDER_FILTERS,
    })


PREVIOUS_STATUS = {  # one step back, for when staff click the wrong button
    'preparing': ('confirmed', 'Back to Confirmed'),
    'ready': ('preparing', 'Back to Preparing'),
    'collected': ('ready', 'Back to Ready for pickup'),
}


def order_detail(request, order_id):
    order = get_object_or_404(Order, pk=order_id)

    next_status = None
    next_label = None
    if order.status == 'confirmed':
        next_status = 'preparing'
        next_label = 'Mark as preparing'
    elif order.status == 'preparing':
        next_status = 'ready'
        next_label = 'Mark as ready for pickup'
    elif order.status == 'ready':
        next_status = 'collected'
        next_label = 'Mark as collected'

    back_status, back_label = PREVIOUS_STATUS.get(order.status, (None, None))

    if request.method == 'POST' and request.POST.get('from_status') == order.status:
        #only moves if nobody changed the status in the meantime, e.g. the customer cancelled
        new_status = back_status if request.POST.get('action') == 'back' else next_status
        if new_status:
            Order.objects.filter(pk=order.pk, status=order.status).update(status=new_status)
        return redirect('dashboard:order_detail', order_id=order.id)

    items = order.items.all()
    return render(request, 'dashboard/order_detail.html',
                  {'order': order, 'items': items, 'next_label': next_label, 'back_label': back_label})

LOW_STOCK = 5  # 1 to 5 left counts as low stock, here and on the dashboard
MAX_STOCK = 9999  # a sanity limit, so a typo like 30000 is caught
INVENTORY_FILTERS = [('', 'All meals'), ('sold_out', 'Sold out'), ('low', 'Low stock'), ('in_stock', 'In stock')]
INVENTORY_SORTS = {
    'meal': ['meal__name'],
    'sold': ['quantity_sold'],
    'left': ['left'],
}


def stock_status(left):
    if left <= 0:
        return 'Sold out'
    if left <= LOW_STOCK:
        return 'Low stock'
    return 'In stock'


def inventory(request): #this week's stock: filter, search, sort, pages, and one Save for every row on the page
    current = current_menu()  # None when there are no menus yet, which matches no rows
    items = MenuItem.objects.filter(weekly_menu=current).select_related('meal', 'meal__category').annotate(
        left=F('quantity_available') - F('quantity_sold'),
    )

    errors = {}  # item id -> message, shown under that row's box
    error_names = []  # also listed above the table, in case the row is on another page
    typed = {}   # item id -> what staff typed, kept in the box when it couldn't be saved
    if request.method == 'POST':
        saved = []
        for name, value in request.POST.items():
            if not name.startswith('qty_'):
                continue
            item_id = name[len('qty_'):]
            if not item_id.isdigit():
                raise Http404('No such meal on this menu.')  # a made-up id gets "not found", not a crash
            item = get_object_or_404(MenuItem.objects.select_related('meal'), pk=int(item_id), weekly_menu=current)
            value = value.strip()
            if value == str(item.quantity_available):
                continue  # unchanged rows are skipped
            if not value.isdigit():
                errors[item.id] = 'Enter a whole number, 0 or more.'
            elif int(value) > MAX_STOCK:
                errors[item.id] = 'Enter ' + str(MAX_STOCK) + ' or less.'
            # the filter re-checks the sold count at save time, in case an order came in after the page loaded
            elif MenuItem.objects.filter(pk=item.id, quantity_sold__lte=int(value)).update(quantity_available=int(value)):
                saved.append(item.meal.name)
                continue
            else:
                errors[item.id] = 'Can\'t be below the ' + str(item.quantity_sold) + ' sold.'
            typed[item.id] = value
            error_names.append(item.meal.name)
        if saved:
            messages.success(request, 'Saved ' + ', '.join(saved) + '.')
        if not errors:
            if not saved:
                messages.info(request, 'Nothing changed, so nothing was saved.')
            return redirect(request.get_full_path())  # back to the same filter, search, sort and page

    counts = {'': 0, 'sold_out': 0, 'low': 0, 'in_stock': 0}
    for left in items.values_list('left', flat=True):  # one small query for the four tiles
        counts[''] += 1
        if left <= 0:
            counts['sold_out'] += 1
        elif left <= LOW_STOCK:
            counts['low'] += 1
        else:
            counts['in_stock'] += 1

    show = request.GET.get('show', '')
    q = request.GET.get('q', '').strip()
    if show == 'sold_out':
        items = items.filter(left__lte=0)
    elif show == 'low':
        items = items.filter(left__gte=1, left__lte=LOW_STOCK)
    elif show == 'in_stock':
        items = items.filter(left__gt=LOW_STOCK)
    else:
        show = ''
    if q:
        items = items.filter(Q(meal__name__icontains=q) | Q(meal__category__name__icontains=q))

    # Fewest left first by default, so sold-out and low-stock meals are at the top
    sort = request.GET.get('sort', 'left')
    key = sort.lstrip('-')
    if key not in INVENTORY_SORTS:
        sort, key = 'left', 'left'
    direction = '-' if sort.startswith('-') else ''
    sort = direction + key
    items = items.order_by(*[direction + field for field in INVENTORY_SORTS[key]], 'meal__name', 'id')

    page_obj = Paginator(items, 25).get_page(request.GET.get('page'))
    for item in page_obj:
        item.status = stock_status(item.left)
        item.percent = round(item.quantity_sold * 100 / item.quantity_available) if item.quantity_available else 100
        item.error = errors.get(item.id)
        item.typed = typed.get(item.id, item.quantity_available)

    params = request.GET.copy()
    params.pop('page', None)
    querystring = params.urlencode()
    params.pop('sort', None)
    return render(request, 'dashboard/inventory.html', {
        'menu': current,
        'page_obj': page_obj,
        'error_names': error_names,
        'max_stock': MAX_STOCK,
        'tiles': [(value, label, counts[value]) for value, label in INVENTORY_FILTERS],
        'querystring': querystring,
        'sort_querystring': params.urlencode(),
        'sort': sort,
        'show': show,
        'q': q,
        'menu_dates': menu_labels(current)[0],
    })

TO_PACK = ['confirmed', 'preparing'] #orders that still need making, same as the To prepare filter


def meal_period(slot): #slots starting before 3 pm count as lunch, the rest as dinner
    return 'lunch' if slot.start_time.hour < 15 else 'dinner'


def packing_list(request): #runs when staff visit /dashboard/packing/, shows one day at a time
    today = timezone.localdate()
    days = list(Order.objects.filter(status__in=TO_PACK, pickup_slot__day__gte=today)
                .values_list('pickup_slot__day', flat=True).distinct().order_by('pickup_slot__day'))
    try:
        day = date.fromisoformat(request.GET.get('day', ''))
    except ValueError:
        day = None
    if day not in days: #no day picked, a bad date or a day with nothing to pack: open the first day that has orders
        day = days[0] if days else None

    #one query for the whole day: every item still to pack, with its order, customer, slot and meal
    items = (OrderItem.objects
             .filter(order__status__in=TO_PACK, order__pickup_slot__day=day)
             .select_related('order__user', 'order__pickup_slot__pickup_point', 'menu_item__meal')
             .order_by('order__pickup_slot__start_time', 'order__pickup_slot__pickup_point__name',
                       'order_id', 'menu_item__meal__name'))

    cook = {} #meal name -> lunch, dinner and total for the whole day
    cards = {} #slot id -> that slot's meal totals and bags, in the order above
    for item in items:
        order, slot, name = item.order, item.order.pickup_slot, item.menu_item.meal.name
        period = meal_period(slot)
        row = cook.setdefault(name, {'name': name, 'lunch': 0, 'dinner': 0, 'total': 0})
        row[period] += item.quantity
        row['total'] += item.quantity
        card = cards.setdefault(slot.id, {'slot': slot, 'period': period.capitalize(),
                                          'totals': {}, 'bags': {}, 'meal_count': 0})
        card['totals'][name] = card['totals'].get(name, 0) + item.quantity
        card['meal_count'] += item.quantity
        card['bags'].setdefault(order.id, {'order': order, 'items': []})['items'].append(item)
    for card in cards.values(): #dicts to sorted lists for the template
        card['totals'] = sorted(card['totals'].items())
        card['bags'] = list(card['bags'].values())

    return render(request, 'dashboard/packing_list.html', {
        'days': days,
        'day': day,
        'cook': sorted(cook.values(), key=lambda row: row['name']),
        'cards': list(cards.values()),
        'lunch_count': sum(row['lunch'] for row in cook.values()), #for the All meals row under To cook
        'dinner_count': sum(row['dinner'] for row in cook.values()),
        'meal_count': sum(row['total'] for row in cook.values()),
        'order_count': sum(len(card['bags']) for card in cards.values()),
    })


STAFF_FILTERS = [('', 'All'), (OWNER, 'Owners'), (HR, 'HR'), (STAFF, 'Staff'), ('inactive', 'Inactive')]


def staff_accounts(request): #owners and HR, the middleware already checked the manage_staff permission
    is_owner = request.user.is_superuser

    if request.method == 'POST' and ('toggle_id' in request.POST or 'role_id' in request.POST): #the buttons on each row
        field = 'toggle_id' if 'toggle_id' in request.POST else 'role_id'
        member = get_object_or_404(User, pk=posted_id(request, field), is_staff=True)
        if not can_manage(request.user, member): #your own account, or HR touching an owner or HR
            raise Http404
        if field == 'toggle_id': #Deactivate / Reactivate
            member.is_active = not member.is_active
            member.save()
            messages.success(request, member.username + (' reactivated.' if member.is_active else ' deactivated.'))
        else: #promote or demote
            role = request.POST.get('role', '')
            if not is_owner or role not in ROLE_NAMES: #only owners can change roles
                raise Http404
            set_role(member, role)
            messages.success(request, member.username + ' is now ' + ROLE_NAMES[role] + '.')
        return redirect(request.get_full_path()) #back to the same filter, search and page

    show = request.GET.get('show', '')
    q = request.GET.get('q', '').strip()
    staff = User.objects.filter(is_staff=True).prefetch_related('groups')
    if show == OWNER:
        staff = staff.filter(is_superuser=True)
    elif show == HR:
        staff = staff.filter(is_superuser=False, groups__name='HR')
    elif show == STAFF:
        staff = staff.filter(is_superuser=False).exclude(groups__name='HR')
    elif show == 'inactive':
        staff = staff.filter(is_active=False)
    if q:
        staff = staff.filter(Q(username__icontains=q) | Q(email__icontains=q))
    staff = staff.order_by('-is_superuser', 'username') #owners first, then A to Z

    page_obj = Paginator(staff, 20).get_page(request.GET.get('page'))
    rows = [{
        'member': member,
        'role': role_of(member),
        'role_name': ROLE_NAMES[role_of(member)],
        'can_manage': can_manage(request.user, member),
    } for member in page_obj]
    params = request.GET.copy()
    params.pop('page', None) #page links add their own page number
    return render(request, 'dashboard/staff_accounts.html', {
        'rows': rows, 'page_obj': page_obj, 'querystring': params.urlencode(),
        'is_owner': is_owner, 'role_choices': ROLE_CHOICES,
        'show': show, 'q': q, 'filters': STAFF_FILTERS,
    })


def staff_account_add(request): #runs when owners or HR open /dashboard/staff-accounts/add/
    is_owner = request.user.is_superuser
    form = StaffAccountForm(request.POST or None, can_choose_role=is_owner) #HR's form has no role field
    if request.method == 'POST' and form.is_valid():
        member = User.objects.create_user(
            username=form.cleaned_data['username'],
            email=form.cleaned_data['email'],
            password=form.cleaned_data['password'], #create_user hashes it
        )
        set_role(member, form.cleaned_data.get('role') or STAFF) #no role field means plain Staff
        messages.success(request, member.username + ' added as ' + ROLE_NAMES[role_of(member)] + '.')
        return redirect('dashboard:staff_accounts')
    return render(request, 'dashboard/staff_account_form.html', {'form': form, 'is_owner': is_owner})


def my_account(request): #runs when staff open /dashboard/account/, the middleware already checked they are staff
    return render(request, 'dashboard/my_account.html') #the role comes from the staff_role context processor
