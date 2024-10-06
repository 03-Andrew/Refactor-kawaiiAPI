from django.db import models
from django.contrib.auth.models import User
# Create your models here.

class UserProfile(models.Model):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", 'Admin'
        RECEPTIONIST = "RECEPTIONIST", 'Receptionist'
        GUARD = "GUARD", 'Guard'
        
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='user_profile')
    role = models.CharField(max_length=50, choices=Role.choices)
    
    