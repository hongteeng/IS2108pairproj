from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

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


REVIEW_FILTERS = [("", "All"), ("visible", "Visible"), ("hidden", "Hidden")]


def staff_reviews(request):
    """List reviews for staff, with search, a visible/hidden filter and pages."""
    if not request.user.is_staff:
        return redirect("dashboard:staff_login")
    status = request.GET.get("status", "")
    q = request.GET.get("q", "").strip()
    reviews = Review.objects.select_related("user", "meal").order_by("-created_at", "-id")
    if status == "visible":
        reviews = reviews.filter(is_hidden=False)
    elif status == "hidden":
        reviews = reviews.filter(is_hidden=True)
    if q:
        reviews = reviews.filter(Q(meal__name__icontains=q) | Q(user__username__icontains=q))

    page_obj = Paginator(reviews, 20).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)  # page links add their own page number
    return render(request, "reviews/staff_reviews.html", {
        "page_obj": page_obj,
        "querystring": params.urlencode(),
        "status": status,
        "q": q,
        "filters": REVIEW_FILTERS,
    })


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
    # Go back to the same page, search and filter, but only within this site.
    next_url = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect("dashboard:reviews")
