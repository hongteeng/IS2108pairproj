from django.db import models


class User(models.Model):
    """A CampusBox account for students and staff."""

    username = models.CharField(max_length=50, unique=True)
    password = models.CharField(max_length=128)  # stores the hash only, not the real password
    is_staff = models.BooleanField(default=False)

    def __str__(self):
        return self.username