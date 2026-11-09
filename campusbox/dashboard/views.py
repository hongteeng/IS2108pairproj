from django.contrib.auth import authenticate, login as auth_login
from django.db.models import Count, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from datetime import timedelta
from accounts.models import CustomerProfile
from accounts.forms import LoginForm
from menu.models import Meal
from .forms import MealForm
from django.db.models import ProtectedError
from menu.models import Meal, WeeklyMenu, MenuItem
from menu.utils import current_menu
from orders.models import Order, OrderItem, PickupPoint, PickupSlot
from support.models import SupportTicket
from .forms import MealForm, WeeklyMenuForm, MenuItemForm, PickupPointForm, PickupSlotForm

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
    latest_menu = current_menu()
    to_prepare = Order.objects.filter(
        status__in=["confirmed", "preparing"],
    ).count()
    ready_count = Order.objects.filter(status="ready").count()
    open_tickets = SupportTicket.objects.filter(status="open").count()
    sold_out = 0
    low_stock = 0
    if latest_menu:
        stock_items = MenuItem.objects.filter(weekly_menu=latest_menu).annotate(
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

def meal_add(request):
    if request.method == 'POST':
        form = MealForm(request.POST)
        if form.is_valid():
            meal = Meal(
                name=form.cleaned_data['name'],
                description=form.cleaned_data['description'],
                price_cents=form.cleaned_data['price_cents'],
                calories=form.cleaned_data['calories'],
                protein_g=form.cleaned_data['protein_g'],
                carbs_g=form.cleaned_data['carbs_g'],
                fat_g=form.cleaned_data['fat_g'],
                image_url=form.cleaned_data['image_url'],
                category=form.cleaned_data['category'],
                is_active=form.cleaned_data['is_active'],
            )
            meal.save()
            meal.dietary_tags.set(form.cleaned_data['dietary_tags'])
            meal.allergens.set(form.cleaned_data['allergens'])
            return redirect('dashboard:meal_list')
    else:
        form = MealForm()
    return render(request, 'dashboard/meal_form.html', {'form': form, 'title': 'Add meal'})


def meal_edit(request, meal_id):
    meal = get_object_or_404(Meal, pk=meal_id)
    if request.method == 'POST':
        form = MealForm(request.POST, instance=meal)
        if form.is_valid():
            meal.name = form.cleaned_data['name']
            meal.description = form.cleaned_data['description']
            meal.price_cents = form.cleaned_data['price_cents']
            meal.calories = form.cleaned_data['calories']
            meal.protein_g = form.cleaned_data['protein_g']
            meal.carbs_g = form.cleaned_data['carbs_g']
            meal.fat_g = form.cleaned_data['fat_g']
            meal.image_url = form.cleaned_data['image_url']
            meal.category = form.cleaned_data['category']
            meal.is_active = form.cleaned_data['is_active']
            meal.save()
            meal.dietary_tags.set(form.cleaned_data['dietary_tags'])
            meal.allergens.set(form.cleaned_data['allergens'])
            return redirect('dashboard:meal_list')
    else:
        form = MealForm(instance=meal)
    return render(request, 'dashboard/meal_form.html', {'form': form, 'title': 'Edit meal'})


def meal_delete(request, meal_id):
    meal = get_object_or_404(Meal, pk=meal_id)
    error = None
    if request.method == 'POST':
        try:
            meal.delete()
            return redirect('dashboard:meal_list')
        except ProtectedError:
            error = 'This meal has orders, so it cannot be deleted. Edit it and untick Active instead.'
    return render(request, 'dashboard/meal_confirm_delete.html', {'meal': meal, 'error': error})


def menu_list(request):
    menus = WeeklyMenu.objects.order_by('-week_start')
    return render(request, 'dashboard/menu_list.html', {'menus': menus})


def menu_add(request):
    if request.method == 'POST':
        form = WeeklyMenuForm(request.POST)
        if form.is_valid():
            menu = WeeklyMenu(
                week_start=form.cleaned_data['week_start'],
                order_cutoff=form.cleaned_data['order_cutoff'],
            )
            menu.save()
            return redirect('dashboard:menu_list')
    else:
        form = WeeklyMenuForm()
    return render(request, 'dashboard/menu_form.html', {'form': form, 'title': 'New weekly menu'})

def menu_detail(request, menu_id):
    menu = get_object_or_404(WeeklyMenu, pk=menu_id)
    error = None
    form = MenuItemForm()

    if request.method == 'POST':
        if 'remove_id' in request.POST:
            item = get_object_or_404(MenuItem, pk=request.POST.get('remove_id', ''))
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
    return render(request, 'dashboard/menu_detail.html',
                  {'menu': menu, 'items': items, 'form': form, 'error': error})

def pickup_list(request):
    points = PickupPoint.objects.all()
    return render(request, 'dashboard/pickup_list.html', {'points': points})


def pickup_add(request):
    if request.method == 'POST':
        form = PickupPointForm(request.POST)
        if form.is_valid():
            point = PickupPoint(
                name=form.cleaned_data['name'],
                location=form.cleaned_data['location'],
                is_active=form.cleaned_data['is_active'],
            )
            point.save()
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
            slot = get_object_or_404(PickupSlot, pk=request.POST.get('remove_id', ''))
            try:
                slot.delete()
            except ProtectedError:
                error = 'This slot already has orders, so it cannot be removed.'
        else:
            form = PickupSlotForm(request.POST)
            if form.is_valid():
                if form.cleaned_data['end_time'] <= form.cleaned_data['start_time']:
                    error = 'The end time must be after the start time.'
                else:
                    slot = PickupSlot(
                        pickup_point=point,
                        day=form.cleaned_data['day'],
                        start_time=form.cleaned_data['start_time'],
                        end_time=form.cleaned_data['end_time'],
                        capacity=form.cleaned_data['capacity'],
                    )
                    slot.save()
                    form = PickupSlotForm()

    slots = point.slots.all()
    return render(request, 'dashboard/pickup_detail.html',
                  {'point': point, 'slots': slots, 'form': form, 'error': error})

def order_list(request):
    orders = Order.objects.select_related(
        'user',
        'pickup_slot__pickup_point',
    ).order_by('-created_at')
    return render(request, 'dashboard/order_list.html', {'orders': orders})


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

    if request.method == 'POST' and next_status is not None:
        order.status = next_status
        order.save()
        return redirect('dashboard:order_detail', order_id=order.id)

    items = order.items.all()
    return render(request, 'dashboard/order_detail.html',
                  {'order': order, 'items': items, 'next_label': next_label})

def inventory(request):
    error = None

    if request.method == 'POST':
        item = get_object_or_404(MenuItem, pk=request.POST.get('item_id', ''))
        new_quantity = request.POST.get('quantity', '')
        if new_quantity.isdigit() and int(new_quantity) >= item.quantity_sold:
            item.quantity_available = int(new_quantity)
            item.save()
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
    })