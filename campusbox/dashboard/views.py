from django.contrib.auth import authenticate, login as auth_login
from django.shortcuts import redirect, render
from accounts.forms import LoginForm
from menu.models import Meal
from .forms import MealForm
from django.db.models import ProtectedError

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