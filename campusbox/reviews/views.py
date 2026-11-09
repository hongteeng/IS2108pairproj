from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, redirect, render

from menu.models import Meal
from orders.models import OrderItem

from .forms import ReviewForm
from .models import Review


@login_required
def add_review(request, meal_id):
    """Add or edit a review for a collected meal."""
    meal = get_object_or_404(Meal, id=meal_id)
    can_review = OrderItem.objects.filter(
        order__user=request.user,
        order__status="collected",
        menu_item__meal=meal,
    ).exists()
    if not can_review:
        messages.error(request, "You can review a meal after you’ve collected it.")
        return redirect("menu:meal_detail", meal_id=meal.id)

    review = Review.objects.filter(user=request.user, meal=meal).first()
    form = ReviewForm(request.POST or None, instance=review)
    if request.method == "POST" and form.is_valid():
        review = form.save(commit=False)
        review.user = request.user
        review.meal = meal
        review.save()
        messages.success(request, "Thanks for your review!")
        return redirect("menu:meal_detail", meal_id=meal.id)

    return render(request, "reviews/review_form.html", {
        "form": form,
        "meal": meal,
        "is_edit": review is not None,
    })


def staff_reviews(request):
    """List all reviews for staff."""
    if not request.user.is_staff:
        return redirect("dashboard:staff_login")
    reviews = Review.objects.select_related("user", "meal").order_by("-created_at")
    return render(request, "reviews/staff_reviews.html", {"reviews": reviews})


@require_POST
def staff_toggle_review(request, review_id):
    """Toggle a review's hidden status for staff."""
    if not request.user.is_staff:
        return redirect("dashboard:staff_login")
    review = get_object_or_404(Review, id=review_id)
    review.is_hidden = not review.is_hidden
    review.save()
    message = "Review hidden." if review.is_hidden else "Review shown again."
    messages.success(request, message)
    return redirect("dashboard:reviews")
