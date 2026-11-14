from django.contrib import messages
from django.shortcuts import redirect

OWNER_ONLY = ['/dashboard/seed/']  #Reset demo data wipes everything, so only owners may use it
NEEDS_PERMISSION = {'/dashboard/staff-accounts/': 'dashboard.manage_staff'}  #owners and HR

#guard that stands at door of whole website. every request goes through it before reaching any view
def staff_only_middleware(get_response):
    def middleware(request):
        path = request.path
        is_staff_page = path.startswith('/dashboard/')
        is_login_page = path == '/dashboard/login/'

        if is_staff_page and not is_login_page:
            if not (request.user.is_authenticated and request.user.is_staff):
                return redirect('dashboard:staff_login')
            #logged in as staff, now check the role (as in Lab 11)
            needed = NEEDS_PERMISSION.get(path)
            if (path in OWNER_ONLY and not request.user.is_superuser) or (needed and not request.user.has_perm(needed)):
                messages.error(request, "You don't have access to that page.")
                return redirect('dashboard:home')

        return get_response(request)
    return middleware