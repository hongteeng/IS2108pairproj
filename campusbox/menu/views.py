import math

from django.db.models import Avg, Case, Q, When
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from accounts.models import CustomerProfile
from accounts.services import get_profile, mark_allergens
from ml.services.suggestions import suggest_for_meals
from .models import MealCategory, DietaryTag, Allergen, Meal, WeeklyMenu, MenuItem
from .utils import current_menu, menu_labels, ordering_open
from datetime import date, timedelta
from orders.models import Order, OrderItem, PickupPoint, PickupSlot
from django.utils.text import slugify

#views.py holds functions that run when someone vists an address
def seed(request): #seed is a batch of starting data for empty database, 
    #for demo n testing. fake starting data
    OrderItem.objects.all().delete()
    Order.objects.all().delete()
    MenuItem.objects.all().delete()
    WeeklyMenu.objects.all().delete()
    Meal.objects.all().delete()
    PickupSlot.objects.all().delete()
    PickupPoint.objects.all().delete()
    
    # Reuse existing categories, tags and allergens so students' quiz answers stay linked.
    for name in ["High-Protein", "Asian Rice Bowls", "Vegetarian", "Low-Carb", "Western", "Comfort"]:
        MealCategory.objects.get_or_create(name=name)

    for name in ["halal", "vegetarian", "vegan", "high-protein"]:
        DietaryTag.objects.get_or_create(name=name)

    for name in ["nuts", "dairy", "shellfish", "gluten", "egg", "fish", "soy"]:
        Allergen.objects.get_or_create(name=name)

    meals = [
        ["Chicken Rice Box", "Steamed chicken, rice, cucumber", 650, 520, 35, 70, 12, "Asian Rice Bowls", ["halal"], ["soy"]],
        ["Teriyaki Salmon Bowl", "Grilled salmon on rice with greens", 890, 610, 38, 65, 20, "High-Protein", [], ["fish", "soy"]],
        ["Tofu Veggie Stir Fry", "Tofu and mixed vegetables with rice", 580, 450, 22, 68, 11, "Vegetarian", ["vegetarian", "vegan", "halal"], ["soy"]],
        ["Beef Burrito Bowl", "Beef, beans, corn and rice", 820, 700, 40, 80, 22, "High-Protein", [], ["dairy"]],
        ["Egg Fried Rice Set", "Egg fried rice with side greens", 520, 560, 18, 85, 15, "Comfort", ["vegetarian"], ["egg", "soy"]],
        ["Protein Pasta", "Chicken pasta with tomato sauce", 750, 640, 42, 75, 16, "High-Protein", ["high-protein"], ["gluten", "dairy"]],
        ["Honey Soy Chicken Bowl", "Honey soy chicken thigh with brown rice", 680, 560, 36, 66, 14, "Asian Rice Bowls", ["halal"], ["soy"]],
        ["Laksa Noodle Bowl", "Light laksa with prawns and tofu puffs", 720, 590, 28, 72, 19, "Asian Rice Bowls", [], ["shellfish", "gluten"]],
        ["Mushroom Barley Risotto", "Creamy mushroom barley with greens", 610, 480, 16, 78, 12, "Vegetarian", ["vegetarian"], ["dairy", "gluten"]],
        ["Tuna Mayo Onigiri Set", "Two onigiri with tuna mayo and miso soup", 540, 470, 24, 70, 10, "Asian Rice Bowls", [], ["fish", "egg", "soy"]],
        ["Satay Chicken Wrap", "Grilled chicken satay with veg in a wrap", 630, 540, 32, 58, 18, "Western", ["halal"], ["nuts", "gluten"]],
        ["Vegan Chickpea Curry", "Chickpea curry with basmati rice", 590, 500, 18, 80, 12, "Vegetarian", ["vegetarian", "vegan", "halal"], []],
        ["Baked Fish and Sweet Potato", "Baked white fish with sweet potato mash", 780, 520, 38, 55, 14, "Low-Carb", ["high-protein"], ["fish"]],
        ["Pork Bulgogi Rice Bowl", "Korean-style pork with rice and kimchi", 760, 650, 34, 76, 20, "Asian Rice Bowls", [], ["soy"]],
        ["Greek Chicken Salad", "Chicken, feta, olives, cucumber and pita", 700, 430, 36, 30, 18, "Low-Carb", ["halal", "high-protein"], ["dairy"]],
        ["Soba Veggie Noodles", "Cold soba with edamame and sesame", 560, 440, 17, 72, 9, "Vegetarian", ["vegetarian", "vegan"], ["gluten", "soy"]],
        ["Egg Mayo Sandwich Set", "Egg mayo wholemeal sandwich with fruit", 480, 420, 20, 50, 16, "Comfort", ["vegetarian"], ["egg", "gluten"]],
        ["Mee Goreng Protein Style", "Wok-fried noodles with egg and chicken", 650, 610, 30, 82, 17, "Comfort", ["halal"], ["egg", "gluten", "soy"]],
        ["Salmon Poke Bowl", "Raw salmon, avocado, edamame, rice", 950, 620, 34, 68, 24, "High-Protein", ["high-protein"], ["fish", "soy"]],
        ["Turkey Meatball Pasta", "Turkey meatballs with whole-wheat pasta", 730, 630, 40, 72, 15, "Western", ["high-protein"], ["gluten", "egg"]],
    ]

    for m in meals:
        meal = Meal(
            name=m[0],
            description=m[1],
            price_cents=m[2],
            calories=m[3],
            protein_g=m[4],
            carbs_g=m[5],
            fat_g=m[6],
            image_url="/static/menu/meals/" + slugify(m[0]) + ".jpg",
            category=MealCategory.objects.get(name=m[7]),
            is_active=True,
        )
        meal.save()
        for tag_name in m[8]:
            meal.dietary_tags.add(DietaryTag.objects.get(name=tag_name))
        for allergen_name in m[9]:
            meal.allergens.add(Allergen.objects.get(name=allergen_name))

  # One weekly menu that contains every meal
    next_monday = date.today() + timedelta(days=7 - date.today().weekday())
    cutoff_day = next_monday - timedelta(days=1)
    week = WeeklyMenu(week_start=next_monday, order_cutoff=str(cutoff_day) + " 23:59")
    week.save()
    for meal in Meal.objects.all():
        item = MenuItem(weekly_menu=week, meal=meal, quantity_available=30, quantity_sold=0)
        item.save()
    # One pickup point with three slots
    point = PickupPoint(name="Sheares Hall Lobby", location="Ground floor, near the mailboxes", is_active=True)
    point.save()
    slots = [
        [next_monday + timedelta(days=1), "12:00", "13:00"],
        [next_monday + timedelta(days=1), "18:00", "19:00"],
        [next_monday + timedelta(days=2), "12:00", "13:00"],
    ]
    for s in slots:
        slot = PickupSlot(pickup_point=point, day=s[0], start_time=s[1], end_time=s[2], capacity=20)
        slot.save()

    messages.success(request, "Seeded " + str(Meal.objects.count()) + " meals.")
    return redirect("dashboard:home")


def weekly_menu(request):
    """Display the current weekly menu and its active meals."""

    menu = current_menu()
    menu_dates, order_deadline = menu_labels(menu)
    categories = MealCategory.objects.order_by('name')
    tags = DietaryTag.objects.order_by('name')
    allergens = Allergen.objects.order_by('name')
    category_id = request.GET.get('category', '')
    diet_id = request.GET.get('diet', '')
    q = request.GET.get('q', '').strip()
    avoid = request.GET.getlist('avoid')
    hide_profile_allergens = False
    recommended_category_id = None
    recommended_category_name = None
    profile = get_profile(request.user) if request.user.is_authenticated else None
    if profile and profile.predicted_category:
        recommended_category_id = profile.predicted_category_id
        recommended_category_name = profile.predicted_category.name
    # Pre-hide the student's allergens until they submit the filter form themselves,
    # and once right after logging in, on top of any filters chosen before.
    just_logged_in = request.session.pop('apply_allergens', False)
    if profile and ('filtered' not in request.GET or just_logged_in):
        saved = [str(allergen_id) for allergen_id in profile.allergies.values_list('id', flat=True)]
        avoid = list(dict.fromkeys(avoid + saved))  # merge, no duplicates
        hide_profile_allergens = bool(saved)  # only show the note if they have allergies
    max_price = request.GET.get('max_price', '')
    max_calories = request.GET.get('max_calories', '')
    min_protein = request.GET.get('min_protein', '')
    total_count = 0
    price_min = price_max = '0.00'
    price_max_limit = 0
    calories_min = calories_max = 0
    protein_min = protein_max = 0

    if menu is None:
        items = []
    else:
        active_items = menu.items.filter(
            meal__is_active=True,
        ).select_related('meal', 'meal__category').prefetch_related('meal__allergens')
        active_item_list = list(active_items)
        total_count = len(active_item_list)
        if active_item_list:
            prices = [item.meal.price_cents / 100 for item in active_item_list]
            calories = [item.meal.calories for item in active_item_list]
            price_min = f"{min(prices):.2f}"
            price_max = f"{max(prices):.2f}"
            price_max_limit = math.ceil(max(prices))
            calories_min = min(calories)
            calories_max = max(calories)
            proteins = [item.meal.protein_g for item in active_item_list]
            protein_min = min(proteins)
            protein_max = max(proteins)

        items = active_items
        if q:
            items = items.filter(
                Q(meal__name__icontains=q) |
                Q(meal__description__icontains=q)
            )
        # Ignore anything that isn't a number, so edited URLs can't crash the page.
        if category_id.isdigit():
            items = items.filter(meal__category_id=category_id)
        if diet_id.isdigit():
            items = items.filter(meal__dietary_tags__id=diet_id).distinct()
        avoid_ids = [a for a in avoid if a.isdigit()]
        if avoid_ids:
            items = items.exclude(meal__allergens__id__in=avoid_ids)
        if max_price.isdigit():
            items = items.filter(meal__price_cents__lte=int(max_price) * 100)
        if max_calories.isdigit():
            items = items.filter(meal__calories__lte=int(max_calories))
        if min_protein.isdigit():
            items = items.filter(meal__protein_g__gte=int(min_protein))
        if recommended_category_id is not None:
            items = items.order_by(
                Case(
                    When(meal__category_id=recommended_category_id, then=0),
                    default=1,
                ),
                'meal__category__name',
                'meal__name',
            )
        else:
            items = items.order_by('meal__category__name', 'meal__name')

        for item in items:
            item.price_dollars = f"{item.meal.price_cents / 100:.2f}"
            item.stock_left = item.quantity_available - item.quantity_sold
            
    mark_allergens(items, profile)
    return render(request, 'menu/weekly_menu.html', {
        'menu': menu,
        'menu_dates': menu_dates,
        'order_deadline': order_deadline,
        'items': items,
        'categories': categories,
        'tags': tags,
        'allergens': allergens,
        'selected_category': category_id,
        'selected_diet': diet_id,
        'selected_q': q,
        'selected_avoid': avoid,
        'max_price': max_price,
        'max_calories': max_calories,
        'selected_min_protein': min_protein,
        'total_count': total_count,
        'price_min': price_min,
        'price_max': price_max,
        'price_max_limit': price_max_limit,
        'calories_min': calories_min,
        'calories_max': calories_max,
        'protein_min': protein_min,
        'protein_max': protein_max,
        'hide_profile_allergens': hide_profile_allergens,
        'recommended_category_id': recommended_category_id,
        'recommended_category_name': recommended_category_name,
        'ordering_open': ordering_open(menu),
    })


def meal_detail(request, meal_id):
    """Display details and availability for one active meal."""

    # 404 instead of a crash if the id doesn't exist or the meal is hidden.
    meal = get_object_or_404(
        Meal.objects.select_related('category'),
        id=meal_id,
        is_active=True,
    )
    menu = current_menu()
    menu_item = None
    if menu:
        menu_item = menu.items.filter(meal=meal).first()
        if menu_item:
            menu_item.stock_left = menu_item.quantity_available - menu_item.quantity_sold

    warning_allergens = Allergen.objects.none()
    if request.user.is_authenticated:
        profile = CustomerProfile.objects.filter(user=request.user).first()
        if profile:
            # Only the allergens this student told us about in the quiz.
            warning_allergens = meal.allergens.filter(
                id__in=profile.allergies.values('id'),
            )

    reviews = meal.reviews.filter(is_hidden=False).select_related('user')
    review_count = reviews.count()
    average = reviews.aggregate(avg_rating=Avg('rating'))['avg_rating']
    avg_rating = round(average, 1) if average is not None else None
    can_review = request.user.is_authenticated and OrderItem.objects.filter(
        order__user=request.user,
        order__status='collected',
        menu_item__meal=meal,
    ).exists()
    suggestions = suggest_for_meals([meal.name])
    for item in suggestions:
        item.price_dollars = f"{item.meal.price_cents / 100:.2f}"
        item.stock_left = item.quantity_available - item.quantity_sold
        
    mark_allergens(suggestions, get_profile(request.user) if request.user.is_authenticated else None)

    return render(request, 'menu/meal_detail.html', {
        'meal': meal,
        'price_dollars': f"{meal.price_cents / 100:.2f}",
        'category': meal.category,
        'dietary_tags': meal.dietary_tags.all(),
        'allergens': meal.allergens.all(),
        'menu_item': menu_item,
        'warning_allergens': warning_allergens,
        'reviews': reviews,
        'avg_rating': avg_rating,
        'review_count': review_count,
        'can_review': can_review,
        'suggestions': suggestions,
        'ordering_open': ordering_open(menu),
    })