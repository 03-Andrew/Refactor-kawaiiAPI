from django.db import models
from django.contrib.auth.models import AbstractUser


class CustomUser(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'Admin'
        RECEPTIONIST = 'RECEPTIONIST', 'Receptionist'
        GUARD = 'GUARD', 'Guard'

    role = models.CharField(max_length=50, choices=Role.choices, default=Role.RECEPTIONIST)
