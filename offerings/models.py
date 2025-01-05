from django.db import models

# Create your models here.
   
class Amenities(models.Model):
    amenity = models.CharField(max_length=100)
    rate_per_head = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.amenity}"
    
class Activity(models.Model):
    activity = models.CharField(max_length=100)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2)
    
    def __str__(self):
        return self.activity

class FoodType(models.Model):
    name = models.CharField(max_length=100)
    def __str__(self):
        return f"{self.name}"
    
class Food(models.Model):
    food_type = models.ForeignKey(FoodType, on_delete=models.CASCADE, related_name='food')
    name = models.CharField(max_length=100)
    description = models.TextField()
    def __str__(self):
        return f"{self.name} {self.description}"
    
class ExtraItems(models.Model):
    item = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return self.item