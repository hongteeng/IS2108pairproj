from django.contrib.auth.hashers import check_password, make_password
from django.shortcuts import redirect, render

from .forms import LoginForm, RegisterForm
from .models import User


def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = User.objects.create(
                username=form.cleaned_data['username'],
                password=make_password(form.cleaned_data['password']),
            )
            request.session['user_id'] = user.id
            request.session['username'] = user.username
            request.session['is_staff'] = user.is_staff
            return redirect('index')
    else:
        form = RegisterForm()
    return render(request, 'accounts/register.html', {'form': form})


def login(request):
    error = None
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            user = User.objects.filter(username=form.cleaned_data['username']).first()
            if user and check_password(form.cleaned_data['password'], user.password):
                request.session['user_id'] = user.id
                request.session['username'] = user.username
                request.session['is_staff'] = user.is_staff
                return redirect('index')
            error = 'Incorrect username or password.'
    else:
        form = LoginForm()
    return render(request, 'accounts/login.html', {'form': form, 'error': error})


def logout(request):
    if request.method == 'POST':
        request.session.flush()
    return redirect('index')