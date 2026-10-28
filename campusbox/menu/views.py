from django.http import HttpResponse
from .models import MealCategory, DietaryTag, Allergen, Meal, WeeklyMenu, MenuItem
from orders.models import PickupPoint, PickupSlot

#views.py holds functions that run when someone vists an address
def seed(request): #seed is a batch of starting data for empty database, 
    #for demo n testing. fake starting data
    MenuItem.objects.all().delete()
    WeeklyMenu.objects.all().delete()
    Meal.objects.all().delete()
    DietaryTag.objects.all().delete()
    Allergen.objects.all().delete()
    PickupSlot.objects.all().delete() #clear data 
    PickupPoint.objects.all().delete()

    for name in ["High-Protein", "Asian Rice Bowls", "Vegetarian", "Low-Carb", "Western", "Comfort"]:
        category = MealCategory(name=name)
        category.save()

    for name in ["halal", "vegetarian", "vegan", "high-protein"]:
        tag = DietaryTag(name=name)
        tag.save()

    for name in ["nuts", "dairy", "shellfish", "gluten", "egg", "fish", "soy"]:
        allergen = Allergen(name=name)
        allergen.save()

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
            image_url="https://via.placeholder.com/300",
            category=MealCategory.objects.get(name=m[7]),
            is_active=True,
        )
        meal.save()
        for tag_name in m[8]:
            meal.dietary_tags.add(DietaryTag.objects.get(name=tag_name))
        for allergen_name in m[9]:
            meal.allergens.add(Allergen.objects.get(name=allergen_name))

  # One weekly menu that contains every meal
    week = WeeklyMenu(week_start="2026-11-02", order_cutoff="2026-11-01 23:59")
    week.save()
    for meal in Meal.objects.all():
        item = MenuItem(weekly_menu=week, meal=meal, quantity_available=30, quantity_sold=0)
        item.save()

    # One pickup point with three slots
    point = PickupPoint(name="Sheares Hall Lobby", location="Ground floor, near the mailboxes", is_active=True)
    point.save()
    slots = [
        ["2026-11-03", "12:00", "13:00"],
        ["2026-11-03", "18:00", "19:00"],
        ["2026-11-04", "12:00", "13:00"],
    ]
    for s in slots:
        slot = PickupSlot(pickup_point=point, day=s[0], start_time=s[1], end_time=s[2], capacity=20)
        slot.save()

    return HttpResponse("Seeded " + str(Meal.objects.count()) + " meals")