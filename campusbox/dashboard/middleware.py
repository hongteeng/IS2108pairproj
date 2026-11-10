from django.shortcuts import redirect

#guard that stands at door of whole website. every request goes through it before reaching any view
def staff_only_middleware(get_response):
    def middleware(request):
        path = request.path
        is_staff_page = path.startswith('/dashboard/')
        is_login_page = path == '/dashboard/login/'

        if is_staff_page and not is_login_page:
            if not (request.user.is_authenticated and request.user.is_staff):
                return redirect('dashboard:staff_login')

        return get_response(request)
    return middleware