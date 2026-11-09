from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login    # renamed so they don't clash
from django.contrib.auth import logout as auth_logout  # with our login/logout views
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect, render

from reviews.models import Review
from support.models import SupportTicket

from .forms import LoginForm, RegisterForm, TasteQuizForm
from .models import CustomerProfile
from .services import predict_preferred_category


def register(request):
    """Show the sign-up form, or create the account and log the user in."""
    
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password'], # hash before saving
            )
            auth_login(request, user)
            return redirect('accounts:quiz')
    else:
        form = RegisterForm()
    return render(request, 'accounts/register.html', {'form': form})


def login(request):
    """Show the login form, or check the credentials and log the user in."""
    
    error = None
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            # Returns the user if the password matches, otherwise None.
            user = authenticate(
                request,
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password'],
            )
            # Same message for every failure so the page doesn’t reveal which accounts exist.
            if user is None or user.is_staff:
                error = 'Incorrect username or password.'
            else:
                auth_login(request, user)
                return redirect('index')
    else:
        form = LoginForm()
    return render(request, 'accounts/login.html', {'form': form, 'error': error})


def logout(request):
    """Clear the session. POST only, so a link can't log anyone out."""
    
    is_staff = request.user.is_staff
    if request.method == 'POST':
        auth_logout(request)
    response = redirect('dashboard:staff_login' if is_staff else 'index')
    # Tells the browser to drop cached copies of this site’s pages on logout.
    response["Clear-Site-Data"] = '"cache"'
    return response

@login_required
def quiz(request):
    """Show or save the logged-in user's taste preferences."""

    profile = CustomerProfile.objects.filter(user=request.user).first()
    if request.method == 'POST':
        form = TasteQuizForm(request.POST, instance=profile)
        if form.is_valid():
            profile = form.save(commit=False) # not saved yet: user and category still missing
            profile.user = request.user
            profile.predicted_category = predict_preferred_category(profile)
            profile.save()
            form.save_m2m() # allergies can only be saved once the profile exists
            return redirect('index')
    else:
        form = TasteQuizForm(instance=profile)
    return render(request, 'accounts/quiz.html', {'form': form})


def staff_customers(request):
    """List non-staff customers and their order totals."""

    if not request.user.is_staff:
        return redirect("dashboard:staff_login")
    q = request.GET.get("q", "").strip()
    customers = User.objects.filter(is_staff=False).select_related(
        "profile__predicted_category",
    ).annotate(
        order_count=Count("orders", filter=~Q(orders__status="cancelled")),
        total_spent_cents=Coalesce(
            Sum("orders__total_cents", filter=~Q(orders__status="cancelled")),
            Value(0),
        ),
    ).order_by("-date_joined")
    if q:
        customers = customers.filter(Q(username__icontains=q) | Q(email__icontains=q))
    for customer in customers:
        customer.total_spent_dollars = f"{customer.total_spent_cents / 100:.2f}"
    return render(request, "accounts/staff_customers.html", {
        "customers": customers,
        "q": q,
    })


def staff_customer_detail(request, user_id):
    """Show a customer's profile, orders, reviews, and tickets."""

    if not request.user.is_staff:
        return redirect("dashboard:staff_login")
    customer = get_object_or_404(User, id=user_id, is_staff=False)
    profile = CustomerProfile.objects.filter(user=customer).select_related(
        "predicted_category",
    ).first()
    orders = customer.orders.select_related(
        "pickup_slot__pickup_point",
    ).order_by("-created_at")
    for order in orders:
        order.total_dollars = f"{order.total_cents / 100:.2f}"
    reviews = customer.reviews.select_related("meal")
    tickets = customer.tickets.select_related("order")
    return render(request, "accounts/staff_customer_detail.html", {
        "customer": customer,
        "profile": profile,
        "orders": orders,
        "reviews": reviews,
        "tickets": tickets,
    })