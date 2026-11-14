from django.contrib.auth import authenticate, login as auth_login
from django.contrib import messages
from django.contrib.auth.models import User
from django.http import Http404
from django.core.paginator import Paginator
from django.db.models import Count, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from datetime import datetime, time, timedelta
from accounts.models import CustomerProfile
from accounts.forms import LoginForm, RegisterForm
from django.db.models import ProtectedError
from menu.models import Meal, WeeklyMenu, MenuItem
from menu.utils import current_menu, menu_labels
from orders.models import Order, OrderItem, PickupPoint, PickupSlot
from support.models import SupportTicket
from .forms import MealForm, WeeklyMenuForm, MenuItemForm, PickupPointForm, PickupSlotForm


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
            stock_remaining__lte=5,
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

def meal_list(request):
    meals = Meal.objects.select_related('category').order_by('category__name', 'name')
    return render(request, 'dashboard/meal_list.html', {'meals': meals})


def meal_edit(request, meal_id):
    meal = get_object_or_404(Meal, pk=meal_id)
    if request.method == 'POST':
        form = MealForm(request.POST, instance=meal)
        if form.is_valid():
            form.save()  # updates this meal because the form was given instance=meal
            return redirect('dashboard:meal_list')
    else:
        form = MealForm(instance=meal)
    return render(request, 'dashboard/meal_form.html', {'form': form, 'title': 'Edit meal'})


def meal_add(request):
    if request.method == 'POST':
        form = MealForm(request.POST)
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
            meal.delete()
            return redirect('dashboard:meal_list')
        except ProtectedError:
            error = 'This meal has orders, so it cannot be deleted. Edit it and switch off "Show on the storefront" instead.'
    return render(request, 'dashboard/meal_confirm_delete.html', {'meal': meal, 'error': error})


def menu_list(request):
    menus = WeeklyMenu.objects.order_by('-week_start')
    return render(request, 'dashboard/menu_list.html', {'menus': menus})


def menu_add(request):
    if request.method == 'POST':
        form = WeeklyMenuForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('dashboard:menu_list')
    else:
        today = timezone.localdate()
        next_monday = today + timedelta(days=7 - today.weekday()) #the next week that has not started yet
        form = WeeklyMenuForm(initial={
            'week_start': next_monday,
            'order_cutoff': datetime.combine(next_monday - timedelta(days=1), time(23, 59)), #Sunday 23:59, the night before
        })
    return render(request, 'dashboard/menu_form.html', {'form': form, 'title': 'New weekly menu'})


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
            item = get_object_or_404(MenuItem, pk=posted_id(request, 'remove_id'))
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

    items = menu.items.all()
    menu_dates, order_deadline = menu_labels(menu)
    return render(request, 'dashboard/menu_detail.html', {
        'menu': menu,
        'menu_dates': menu_dates,
        'order_deadline': order_deadline,
        'items': items,
        'form': form,
        'error': error,
    })

def pickup_list(request):
    points = PickupPoint.objects.all()
    return render(request, 'dashboard/pickup_list.html', {'points': points})


def pickup_add(request):
    if request.method == 'POST':
        form = PickupPointForm(request.POST)
        if form.is_valid():
            point = form.save()
            return redirect('dashboard:pickup_detail', point_id=point.id)
    else:
        form = PickupPointForm()
    return render(request, 'dashboard/pickup_form.html', {'form': form, 'title': 'New pickup point'})


def pickup_detail(request, point_id):
    point = get_object_or_404(PickupPoint, pk=point_id)
    error = None
    form = PickupSlotForm()

    if request.method == 'POST':
        if 'toggle' in request.POST:
            point.is_active = not point.is_active
            point.save()
        elif 'remove_id' in request.POST:
            slot = get_object_or_404(PickupSlot, pk=posted_id(request, 'remove_id'))
            try:
                slot.delete()
            except ProtectedError:
                error = 'This slot already has orders, so it cannot be removed.'
        else:
            form = PickupSlotForm(request.POST)
            if form.is_valid():  # the form checks the day and times
                slot = form.save(commit=False)
                slot.pickup_point = point
                slot.save()
                form = PickupSlotForm()

    slots = point.slots.all()
    return render(request, 'dashboard/pickup_detail.html',
                  {'point': point, 'slots': slots, 'form': form, 'error': error})

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

    if request.method == 'POST' and next_status is not None and request.POST.get('from_status') == order.status:
        order.status = next_status
        order.save()
        return redirect('dashboard:order_detail', order_id=order.id)

    items = order.items.all()
    return render(request, 'dashboard/order_detail.html',
                  {'order': order, 'items': items, 'next_label': next_label})

def inventory(request):
    error = None

    if request.method == 'POST':
        item = get_object_or_404(MenuItem, pk=posted_id(request, 'item_id'))
        new_quantity = request.POST.get('quantity', '')
        if new_quantity.isdigit() and int(new_quantity) >= item.quantity_sold:
            item.quantity_available = int(new_quantity)
            item.save()
            messages.success(request, item.meal.name + ' set to ' + new_quantity + '.')
            return redirect('dashboard:inventory') #redirect so a refresh doesn't save again
        else:
            error = 'Enter a whole number that is at least the number already sold.'

    current = current_menu()
    items = MenuItem.objects.none()
    if current:
        items = MenuItem.objects.filter(
            weekly_menu=current,
        ).select_related(
            'meal',
            'weekly_menu',
        ).order_by('meal__name')

    rows = []
    sold_out_count = 0
    low_count = 0
    for item in items:
        left = item.quantity_available - item.quantity_sold
        if left <= 0:
            status = 'Sold out'
            sold_out_count = sold_out_count + 1
        elif left <= 5:
            status = 'Low stock'
            low_count = low_count + 1
        else:
            status = 'OK'
        rows.append({'item': item, 'left': left, 'status': status})

    return render(request, 'dashboard/inventory.html', {
        'rows': rows,
        'error': error,
        'sold_out_count': sold_out_count,
        'low_count': low_count,
        'menu_dates': menu_labels(current)[0],
    })

def packing_list(request): #runs when staff visit /dashboard/packing/ 
    today = timezone.localdate()
    slots = PickupSlot.objects.filter(day__gte=today).select_related('pickup_point').order_by('day', 'start_time')
    groups = []
    for slot in slots:
        items = (OrderItem.objects
                 .filter(order__pickup_slot=slot, order__status__in=['confirmed', 'preparing'])
                 .values('menu_item__meal__name')
                 .annotate(total=Sum('quantity'))
                 .order_by('menu_item__meal__name'))
        if items:
            groups.append({'slot': slot, 'items': items})
    return render(request, 'dashboard/packing_list.html', {'groups': groups})


def staff_accounts(request): #runs when the owner opens /dashboard/staff-accounts/
    if not request.user.is_superuser: #the middleware already checked is_staff, this keeps normal staff out too
        messages.error(request, 'Only the owner can manage staff accounts.')
        return redirect('dashboard:home')

    form = RegisterForm()
    if request.method == 'POST':
        if 'toggle_id' in request.POST: #the Deactivate / Reactivate buttons
            toggle_id = request.POST['toggle_id']
            if not toggle_id.isdigit():
                raise Http404
            member = get_object_or_404(User, pk=int(toggle_id), is_staff=True, is_superuser=False) #owners can't be switched off
            member.is_active = not member.is_active
            member.save()
            return redirect('dashboard:staff_accounts')
        form = RegisterForm(request.POST) #the Add staff form
        if form.is_valid():
            User.objects.create_user(
                username=form.cleaned_data['username'],
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password'], #create_user hashes it
                is_staff=True,
            )
            messages.success(request, 'Staff account created.')
            return redirect('dashboard:staff_accounts')

    staff = User.objects.filter(is_staff=True).order_by('-is_superuser', 'username')
    return render(request, 'dashboard/staff_accounts.html', {'staff': staff, 'form': form})