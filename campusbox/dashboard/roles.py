"""Staff roles: Owner (a superuser), HR (in the HR group) and Staff (is_staff only)."""

from django.contrib.auth.models import Group, Permission

OWNER = 'owner'
HR = 'hr'
STAFF = 'staff'
ROLE_CHOICES = [(STAFF, 'Staff'), (HR, 'HR'), (OWNER, 'Owner')]
ROLE_NAMES = dict(ROLE_CHOICES)


def hr_group():
    """Return the HR group, creating it with the manage_staff permission the first time."""
    group, created = Group.objects.get_or_create(name='HR')
    if created:
        group.permissions.add(Permission.objects.get(content_type__app_label='dashboard', codename='manage_staff'))
    return group


def role_of(user):
    """Return OWNER, HR or STAFF for a staff account."""
    if user.is_superuser:
        return OWNER
    if any(group.name == 'HR' for group in user.groups.all()):  # uses prefetch_related('groups') when given
        return HR
    return STAFF


def set_role(user, role):
    """Give a staff account a new role and save it."""
    user.is_staff = True
    user.is_superuser = role == OWNER  # superusers pass every has_perm check
    user.save()
    if role == HR:
        user.groups.add(hr_group())
    else:
        user.groups.remove(hr_group())


def can_manage(actor, member):
    """Owners can change any staff account except their own. HR can only change plain staff."""
    if member.pk == actor.pk:
        return False
    if actor.is_superuser:
        return True
    return actor.has_perm('dashboard.manage_staff') and role_of(member) == STAFF
