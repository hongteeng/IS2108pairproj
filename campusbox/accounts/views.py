from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login    # renamed so they don't clash
from django.contrib.auth import logout as auth_logout  # with our login/logout views
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

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
            if user is not None:
                auth_login(request, user)
                return redirect('index')
            error = 'Incorrect username or password.'
    else:
        form = LoginForm()
    return render(request, 'accounts/login.html', {'form': form, 'error': error})


def logout(request):
    """Clear the session. POST only, so a link can't log anyone out."""
    
    if request.method == 'POST':
        auth_logout(request)
    return redirect('index')

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