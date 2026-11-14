from .roles import ROLE_NAMES, role_of


def staff_role(request):
    """The signed-in staff member's role (Owner, HR or Staff), for the navbar."""
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated or not user.is_staff:
        return {}
    return {'staff_role': ROLE_NAMES[role_of(user)]}
