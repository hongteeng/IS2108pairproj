"""Fill the database with fake customers, orders, tickets and reviews for testing.

Orders go into two weeks so the dates make sense: last week (already collected, with tickets and
reviews) and the current menu's week (confirmed, waiting to be cooked)."""

import random
from datetime import datetime, time, timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db.models import F
from django.utils import timezone

from accounts.models import CustomerProfile
from accounts.services import predict_preferred_category
from dashboard.roles import HR, STAFF, set_role
from menu.models import Allergen, MenuItem, WeeklyMenu
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
        parser.add_argument("--customers", type=int, default=50)
        parser.add_argument("--orders", type=int, default=150)

    def handle(self, *args, **options):
        random.seed(2108)  # same data every time it runs
        menu = current_menu()
        slots = self.week_slots(menu) if menu else []
        menu_items = list(menu.items.select_related("meal")) if menu else []
        if not menu_items or not slots:
            raise CommandError("No menu or pickup slots yet. Click Reset demo data on the staff dashboard first.")
        past_menu, past_slots = self.make_past_week(menu, slots)

        self.make_staff()
        customers = self.make_customers(options["customers"])
        now = timezone.now()
        past_count = options["orders"] * 3 // 5  # about 60% last week, 40% this week
        # Last week: ordered in the six days before its cutoff, then collected (a few no-shows and cancellations).
        orders = self.make_orders(
            customers, past_slots, list(past_menu.items.select_related("meal")), past_count,
            statuses=["collected"] * 8 + ["ready"] + ["cancelled"],
            ordered_between=(past_menu.order_cutoff - timedelta(days=6), past_menu.order_cutoff - timedelta(hours=1)),
        )
        # This week: ordered over the last few days and not cooked yet.
        orders += self.make_orders(
            customers, slots, menu_items, options["orders"] - past_count,
            statuses=["confirmed"] * 9 + ["cancelled"],
            ordered_between=(now - timedelta(days=5), min(now, menu.order_cutoff)),
        )
        tickets = self.make_tickets(customers)
        reviews = self.make_reviews(customers)
        self.stdout.write(self.style.SUCCESS(
            f"Added {len(customers)} customers, {orders} orders, {tickets} tickets "
            f"and {reviews} reviews, plus staff accounts hr01 (HR) and staff01 (Staff). Demo password: {PASSWORD}"
        ))

    def week_slots(self, menu):
        """Pickup slots at active points from Monday to Friday of the menu's week."""
        return list(PickupSlot.objects.filter(
            pickup_point__is_active=True,
            day__range=(menu.week_start, menu.week_start + timedelta(days=4)),
        ))

    def make_past_week(self, menu, slots):
        """Make (or reuse) the last week that has already finished, with the same meals and slot times."""
        today = timezone.localdate()
        days_back = (today.weekday() - 4) % 7 or 7  # back to the most recent Friday before today
        week_start = today - timedelta(days=days_back + 4)
        if week_start >= menu.week_start:  # never reuse the current menu's own week
            week_start = menu.week_start - timedelta(days=7)
        cutoff = timezone.make_aware(datetime.combine(week_start - timedelta(days=1), time(23, 59)))
        past_menu, _ = WeeklyMenu.objects.get_or_create(week_start=week_start, defaults={"order_cutoff": cutoff})
        for item in menu.items.select_related("meal"):
            MenuItem.objects.get_or_create(
                weekly_menu=past_menu, meal=item.meal,
                defaults={"quantity_available": item.quantity_available},
            )
        past_slots = []
        for slot in slots:  # same weekday and times as this week's slots
            past_slot, _ = PickupSlot.objects.get_or_create(
                pickup_point=slot.pickup_point,
                day=week_start + (slot.day - menu.week_start),
                start_time=slot.start_time,
                defaults={"end_time": slot.end_time, "capacity": slot.capacity},
            )
            past_slots.append(past_slot)
        return past_menu, past_slots

    def make_staff(self):
        """Create hr01 (HR) and staff01 (Staff) so each staff role can be shown. Reuses them if they exist."""
        for username, role in [("hr01", HR), ("staff01", STAFF)]:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"email": f"{username}@example.com"},
            )
            if created:
                user.set_password(PASSWORD)
                set_role(user, role)  # also saves the user

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
                user.date_joined = timezone.now() - timedelta(days=random.randint(21, 60))  # before any demo order
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

    def make_orders(self, customers, slots, menu_items, count, statuses, ordered_between):
        """Create orders with 1-3 meals each, respecting stock and slot capacity, placed between the two times."""
        earliest, latest = ordered_between
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

            ordered_at = earliest + (latest - earliest) * random.random()
            # Only customers who had already signed up by then.
            joined = [customer for customer in customers if customer.date_joined <= ordered_at] or customers
            order = Order.objects.create(
                user=random.choice(joined),
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
            # created_at is filled in automatically, so set the order time afterwards.
            Order.objects.filter(id=order.id).update(created_at=ordered_at)
            made += 1
        return made

    def make_tickets(self, customers):
        """Report problems on some ready or collected orders that have no ticket yet."""
        orders = list(Order.objects.filter(
            user__in=customers,
            status__in=["ready", "collected"],
            tickets__isnull=True,
        ).select_related("pickup_slot"))
        made = 0
        for order in random.sample(orders, min(15, len(orders))):
            issue_type = random.choice(list(TICKET_MESSAGES))
            status = random.choice(["open", "open", "resolved", "rejected"])
            ticket = SupportTicket.objects.create(
                user=order.user,
                order=order,
                issue_type=issue_type,
                message=TICKET_MESSAGES[issue_type],
                status=status,
                refund_amount_cents=order.total_cents // 2 if status == "resolved" else 0,
                staff_reply=STAFF_REPLIES[status],
            )
            SupportTicket.objects.filter(id=ticket.id).update(created_at=self.after_pickup(order))
            made += 1
        return made

    def make_reviews(self, customers):
        """Review some meals from collected orders (one review per student per meal)."""
        lines = OrderItem.objects.filter(
            order__user__in=customers,
            order__status="collected",
        ).select_related("order__user", "order__pickup_slot", "menu_item__meal")
        made = 0
        for line in lines:
            if random.random() < 0.6:
                rating = random.choice([5, 5, 4, 4, 4, 3, 2, 1])
                review, created = Review.objects.get_or_create(
                    user=line.order.user,
                    meal=line.menu_item.meal,
                    defaults={"rating": rating, "comment": REVIEW_COMMENTS[rating]},
                )
                if created:
                    Review.objects.filter(id=review.id).update(created_at=self.after_pickup(line.order))
                    made += 1
        return made

    def after_pickup(self, order):
        """A time up to two days after the order's pickup, but not in the future."""
        pickup = timezone.make_aware(datetime.combine(order.pickup_slot.day, order.pickup_slot.end_time))
        return min(pickup + timedelta(hours=random.randint(1, 48)), timezone.now())
