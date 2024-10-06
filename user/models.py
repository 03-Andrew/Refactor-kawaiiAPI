from django.db import models
from django.contrib.auth.models import AbstractUser
# Create your models here.

class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", 'Admin'
        RECEPTIONIST = "RECEPTIONIST", 'Receptionist'
        GUARD = "GUARD", 'Guard'
        
        
    base_role = Role.ADMIN
    role = models.CharField(max_length=50, choices=Role.choices)
    
    def save(self, *args, **kwargs):
        if not self.pk: 
            set.role = self.base_role
            return super().save(*args, **kwargs)
        

class Receptionist(User):
    base_role = User.Role.RECEPTIONIST
    
    class Meta:
        proxy = True
        
    