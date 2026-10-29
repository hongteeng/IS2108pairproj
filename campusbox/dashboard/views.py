from django.contrib.auth import authenticate, login as auth_login
from django.shortcuts import redirect, render
from accounts.forms import LoginForm


def staff_login(request): #function to authenticate user, runs when visiting /dashboard/login
    error = None
    if request.method == 'POST': #post vs GET. POST means clicking on login button. GET means view, clicking on link going to website
        form = LoginForm(request.POST)
        if form.is_valid():
            user = authenticate(
                request,
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password'],
            )
            if user is not None and user.is_staff:
                auth_login(request, user)
                return redirect('dashboard:home') #send them to the dashboard
            error = 'This login is for staff only.'
    else:
        form = LoginForm()
    return render(request, 'dashboard/staff_login.html', {'form': form, 'error': error})

def home(request):
    return render(request, 'dashboard/home.html')