from django.contrib import messages
from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login    # renamed so they don't clash
from django.contrib.auth import logout as auth_logout  # with our login/logout views
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect, render
from django.core.paginator import Paginator
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm

from django.utils.http import url_has_allowed_host_and_scheme

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
                request.session['apply_allergens'] = True  # menu hides their allergens on the next visit
                # Go back to the page that asked them to log in, but only within this site.
                next_url = request.GET.get('next', '')
                if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                    return redirect(next_url)
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

OPEN_ORDER_STATUSES = ['confirmed', 'preparing', 'ready'] #orders that still need to be made or collected


@login_required
def deactivate_account(request):
    """Ask the customer to confirm, then switch their account off (is_active False). Nothing is deleted."""

    if request.user.is_staff:
        return redirect('dashboard:home') #staff accounts are handled by the owner in the dashboard
    open_orders = request.user.orders.filter(status__in=OPEN_ORDER_STATUSES).count()
    if request.method == 'POST' and open_orders == 0:
        request.user.is_active = False
        request.user.save()
        auth_logout(request)
        messages.success(request, 'Your account has been deactivated.')
        response = redirect('index')
        response["Clear-Site-Data"] = '"cache"'
        return response
    return render(request, 'accounts/deactivate.html', {'open_orders': open_orders})
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
            messages.success(request, "Preferences saved.")
            return redirect('index')
    else:
        form = TasteQuizForm(instance=profile)
    return render(request, 'accounts/quiz.html', {'form': form})


CUSTOMER_SORTS = {
    "username": "username",
    "joined": "date_joined",
    "orders": "order_count",
    "spent": "total_spent_cents",
}


def staff_customers(request):
    """List non-staff customers and their order totals, with search and sorting."""

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
    )
    if q:
        customers = customers.filter(Q(username__icontains=q) | Q(email__icontains=q))

    # ?sort=spent is low to high, ?sort=-spent is high to low. Only the keys above are allowed.
    sort = request.GET.get("sort", "username")  # default: A to Z by username
    key = sort.lstrip("-")
    if key not in CUSTOMER_SORTS:
        sort, key = "username", "username"
    direction = "-" if sort.startswith("-") else ""
    sort = direction + key
    customers = customers.order_by(direction + CUSTOMER_SORTS[key], "id")  # id keeps ties in a fixed order

    page_obj = Paginator(customers, 20).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)  # page links add their own page number
    querystring = params.urlencode()
    params.pop("sort", None)  # sort links add their own sort
    return render(request, "accounts/staff_customers.html", {
        "page_obj": page_obj,
        "querystring": querystring,
        "sort_querystring": params.urlencode(),
        "sort": sort,
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
    reviews = customer.reviews.select_related("meal")
    tickets = customer.tickets.select_related("order")
    return render(request, "accounts/staff_customer_detail.html", {
        "customer": customer,
        "profile": profile,
        "orders": orders,
        "reviews": reviews,
        "tickets": tickets,
    })

@login_required
def change_password(request):
    """Let a logged-in user set a new password (they must type the old one first)."""
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()                      # hashes and saves the new password
        update_session_auth_hash(request, user) # keeps them logged in
        messages.success(request, 'Your password has been changed.')
        return redirect('accounts:quiz')
    return render(request, 'accounts/change_password.html', {'form': form})