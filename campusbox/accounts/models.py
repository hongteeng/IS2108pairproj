from django.db import models


class User(models.Model):
    username = models.CharField(max_length=50, unique=True)
    password = models.CharField(max_length=128)
    is_staff = models.BooleanField(default=False)

    def __str__(self):
        return self.username