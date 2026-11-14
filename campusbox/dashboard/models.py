from django.db import models


class StaffAccess(models.Model):
    """Holds the custom staff permissions, like SecurityModel in Lab 11. It has no rows and no table."""

    class Meta:
        managed = False            # no database table, the model only exists for its permissions
        default_permissions = ()   # skip the usual add/change/delete/view permissions
        permissions = [('manage_staff', 'Can manage staff accounts')]
