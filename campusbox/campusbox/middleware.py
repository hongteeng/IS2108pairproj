from django.contrib import messages
from django.shortcuts import redirect
from django.utils.cache import add_never_cache_headers

# Keep staff out of customer-only pages, opposite of the staff middleware.
def customer_only_middleware(get_response):
    def middleware(request):
        path = request.path
        is_customer_page = path.startswith(('/orders/', '/reviews/', '/support/', '/accounts/quiz/'))

        if is_customer_page and request.user.is_authenticated and request.user.is_staff:
            messages.info(request, "That page is for customers. You’re signed in as staff.")
            return redirect('dashboard:home')

        return get_response(request)
    return middleware

# Stops the browser showing private pages from its cache after logout.
def no_cache_for_logged_in_middleware(get_response):
    def middleware(request):
        response = get_response(request)
        if request.user.is_authenticated:
            add_never_cache_headers(response)
        return response
    return middleware
