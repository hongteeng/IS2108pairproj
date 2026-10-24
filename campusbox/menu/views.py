from django.http import HttpResponse
from .models import Meal, PickupPoint, PickupSlot

#views.py holds functions that run when someone vists an address
def seed(request): #seed is a batch of starting data for empty database, 
    #for demo n testing. fake starting data
    Meal.objects.all().delete()
    PickupSlot.objects.all().delete() #clear data 
    PickupPoint.objects.all().delete()

    meals = [
        ["Chicken Rice Box", "Steamed chicken, rice, cucumber", 650, 520, 35, 70, 12],
        ["Teriyaki Salmon Bowl", "Grilled salmon on rice with greens", 890, 610, 38, 65, 20],
        ["Tofu Veggie Stir Fry", "Tofu and mixed vegetables with rice", 580, 450, 22, 68, 11],
        ["Beef Burrito Bowl", "Beef, beans, corn and rice", 820, 700, 40, 80, 22],
        ["Egg Fried Rice Set", "Egg fried rice with side greens", 520, 560, 18, 85, 15],
        ["Protein Pasta", "Chicken pasta with tomato sauce", 750, 640, 42, 75, 16],
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
            is_available=True,
        )
        meal.save()

    point = PickupPoint(name="Sheares Hall Lobby")
    point.save()
    slot = PickupSlot(pickup_point=point, label="12:00-13:00", capacity=20)
    slot.save()

    return HttpResponse("Seeded " + str(Meal.objects.count()) + " meals")