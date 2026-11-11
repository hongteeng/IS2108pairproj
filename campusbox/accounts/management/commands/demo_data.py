"""Fill the database with fake customers, orders, tickets and reviews for testing."""

import random
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db.models import F
from django.utils import timezone

from accounts.models import CustomerProfile
from accounts.services import predict_preferred_category
from menu.models import Allergen, MenuItem
from menu.utils import current_menu
from orders.models import Order, OrderItem, PickupSlot
from reviews.models import Review
from support.models import SupportTicket

PASSWORD = "Demo1234!"  # every demo account uses this password

TICKET_MESSAGES = {
    "missing_item": "One of my meals was missing from the bag.",
    "wrong_item": "I received a different meal from the one I ordered.",
    "quality": "The food was cold when I collected it.",
    "other": "The pickup point was closed when I arrived.",
}
STAFF_REPLIES = {
    "open": "",
    "resolved": "Sorry about that. We’ve refunded part of your order.",
    "rejected": "We checked with the kitchen and your order was complete.",
}
REVIEW_COMMENTS = {
    5: "Really good, would order again.",
    4: "Tasty and filling.",
    3: "It was okay.",
    2: "A bit bland for me.",
    1: "Not for me, sorry.",
}


class Command(BaseCommand):
    help = "Add demo customers, orders, tickets and reviews. Reset demo data on the staff dashboard first."

    def add_arguments(self, parser):
        parser.add_argument("--customers", type=int, default=30)
        parser.add_argument("--orders", type=int, default=50)

    def handle(self, *args, **options):
        random.seed(2108)  # same data every time it runs
        menu = current_menu()
        slots = list(PickupSlot.objects.filter(pickup_point__is_active=True))
        menu_items = list(menu.items.select_related("meal")) if menu else []
        if not menu_items or not slots:
            raise CommandError("No menu or pickup slots yet. Click Reset demo data on the staff dashboard first.")

        customers = self.make_customers(options["customers"])
        orders = self.make_orders(customers, slots, menu_items, options["orders"])
        tickets = self.make_tickets(customers)
        reviews = self.make_reviews(customers)
        self.stdout.write(self.style.SUCCESS(
            f"Added {len(customers)} customers, {orders} orders, {tickets} tickets "
            f"and {reviews} reviews. Demo password: {PASSWORD}"
        ))

    def make_customers(self, count):
        """Create demo01, demo02, ... with a quiz profile. Reuses ones that already exist."""
        allergens = list(Allergen.objects.all())
        customers = []
        for n in range(1, count + 1):
            username = f"demo{n:02d}"
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"email": f"{username}@example.com"},
            )
            if created:
                user.set_password(PASSWORD)
                user.date_joined = timezone.now() - timedelta(days=random.randint(0, 60))
                user.save()
                profile = CustomerProfile(
                    user=user,
                    age=random.randint(18, 26),
                    gender=random.choice(CustomerProfile.GENDER_CHOICES)[0],
                    is_on_campus=random.random() < 0.8,
                    budget_per_meal=random.randint(5, 10),
                    fitness_goal=random.choice(CustomerProfile.FITNESS_GOAL_CHOICES)[0],
                    spice_tolerance=random.choice(CustomerProfile.SPICE_TOLERANCE_CHOICES)[0],
                    diet=random.choice(["none", "none", "vegetarian", "vegan", "halal"]),
                )
                profile.predicted_category = predict_preferred_category(profile)
                profile.save()
                if allergens and random.random() < 0.3:
                    profile.allergies.add(random.choice(allergens))
            customers.append(user)
        return customers

    def make_orders(self, customers, slots, menu_items, count):
        """Create orders with 1-3 meals each, respecting stock and slot capacity."""
        statuses = ["confirmed"] * 3 + ["preparing"] * 2 + ["ready"] * 2 + ["collected"] * 4 + ["cancelled"]
        made = 0
        for _ in range(count):
            open_slots = [
                slot for slot in slots
                if slot.orders.exclude(status="cancelled").count() < slot.capacity
            ]
            if not open_slots:
                break
            status = random.choice(statuses)
            lines = []
            for item in random.sample(menu_items, random.randint(1, 3)):
                quantity = random.randint(1, 2)
                # Cancelled orders have already given their stock back.
                if status != "cancelled":
                    updated = MenuItem.objects.filter(
                        id=item.id,
                        quantity_sold__lte=F("quantity_available") - quantity,
                    ).update(quantity_sold=F("quantity_sold") + quantity)
                    if not updated:
                        continue
                lines.append((item, quantity))
            if not lines:
                continue

            order = Order.objects.create(
                user=random.choice(customers),
                pickup_slot=random.choice(open_slots),
                status=status,
                total_cents=sum(item.meal.price_cents * quantity for item, quantity in lines),
                payment_reference=f"DEMO-{random.randint(100000, 999999)}",
            )
            for item, quantity in lines:
                OrderItem.objects.create(
                    order=order,
                    menu_item=item,
                    quantity=quantity,
                    price_at_purchase_cents=item.meal.price_cents,
                )
            # created_at is filled in automatically, so spread the orders over the last two weeks afterwards.
            Order.objects.filter(id=order.id).update(
                created_at=timezone.now() - timedelta(days=random.randint(0, 13), hours=random.randint(0, 23)),
            )
            made += 1
        return made

    def make_tickets(self, customers):
        """Report problems on some ready or collected orders that have no ticket yet."""
        orders = list(Order.objects.filter(
            user__in=customers,
            status__in=["ready", "collected"],
            tickets__isnull=True,
        ))
        made = 0
        for order in random.sample(orders, min(15, len(orders))):
            issue_type = random.choice(list(TICKET_MESSAGES))
            status = random.choice(["open", "open", "resolved", "rejected"])
            SupportTicket.objects.create(
                user=order.user,
                order=order,
                issue_type=issue_type,
                message=TICKET_MESSAGES[issue_type],
                status=status,
                refund_amount_cents=order.total_cents // 2 if status == "resolved" else 0,
                staff_reply=STAFF_REPLIES[status],
            )
            made += 1
        return made

    def make_reviews(self, customers):
        """Review some meals from collected orders (one review per student per meal)."""
        lines = OrderItem.objects.filter(
            order__user__in=customers,
            order__status="collected",
        ).select_related("order__user", "menu_item__meal")
        made = 0
        for line in lines:
            if random.random() < 0.6:
                rating = random.choice([5, 5, 4, 4, 4, 3, 2, 1])
                _, created = Review.objects.get_or_create(
                    user=line.order.user,
                    meal=line.menu_item.meal,
                    defaults={"rating": rating, "comment": REVIEW_COMMENTS[rating]},
                )
                if created:
                    made += 1
        return made