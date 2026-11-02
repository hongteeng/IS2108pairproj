from django.contrib.auth import authenticate, login as auth_login
from django.shortcuts import redirect, render
from accounts.forms import LoginForm
from menu.models import Meal
from .forms import MealForm
from django.db.models import ProtectedError
from menu.models import Meal, WeeklyMenu, MenuItem
from orders.models import PickupPoint, PickupSlot
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
            if user is not None and user.is_staff:
                auth_login(request, user)
                return redirect('dashboard:home') #send them to the dashboard
            error = 'This login is for staff only.'
    else:
        form = LoginForm()
    return render(request, 'dashboard/staff_login.html', {'form': form, 'error': error})

def home(request):
    return render(request, 'dashboard/home.html')

def meal_list(request):
    meals = Meal.objects.all()
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
    meal = Meal.objects.get(pk=meal_id)
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
    meal = Meal.objects.get(pk=meal_id)
    error = None
    if request.method == 'POST':
        try:
            meal.delete()
            return redirect('dashboard:meal_list')
        except ProtectedError:
            error = 'This meal has orders, so it cannot be deleted. Edit it and untick Active instead.'
    return render(request, 'dashboard/meal_confirm_delete.html', {'meal': meal, 'error': error})


def menu_list(request):
    menus = WeeklyMenu.objects.all()
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
    menu = WeeklyMenu.objects.get(pk=menu_id)
    error = None
    form = MenuItemForm()

    if request.method == 'POST':
        if 'remove_id' in request.POST:
            item = MenuItem.objects.get(pk=request.POST['remove_id'])
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
    point = PickupPoint.objects.get(pk=point_id)
    error = None
    form = PickupSlotForm()

    if request.method == 'POST':
        if 'toggle' in request.POST:
            point.is_active = not point.is_active
            point.save()
        elif 'remove_id' in request.POST:
            slot = PickupSlot.objects.get(pk=request.POST['remove_id'])
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