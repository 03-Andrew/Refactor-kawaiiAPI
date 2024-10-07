from django.db import models
from transactions.models import Billing
from django.core.exceptions import ValidationError


class Inclusions(models.Model):
    inclusion = models.CharField(max_length=100)

    def __str__(self):
        return self.inclusion


class RoomStatus(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class RoomType(models.Model):
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(null=True, blank=True)
    good_for = models.PositiveSmallIntegerField(null=True)
    max_children = models.PositiveSmallIntegerField(null = True)
    max_adult = models.PositiveSmallIntegerField()
    inclusions = models.ManyToManyField(Inclusions)

    def __str__(self):
        return self.name

class Room(models.Model):
    number = models.CharField(max_length=100, unique=True)
    type = models.ForeignKey(RoomType, on_delete=models.PROTECT, related_name="room")
    status = models.ForeignKey(RoomStatus, on_delete=models.PROTECT, related_name="room")
    

    def __str__(self):
        return f"Room {self.number} - {self.type.name}"


class BookingStatus(models.Model):
    name = models.CharField(max_length=50, null=True)

    def __str__(self):
        return self.name

class Booking(models.Model):
    customer_bill = models.ForeignKey(Billing, on_delete=models.PROTECT,  related_name='bookings')
    room = models.ForeignKey(Room, on_delete=models.PROTECT, null=True, blank=True, related_name='bookings')
    room_type = models.ForeignKey(RoomType, on_delete=models.PROTECT, related_name='bookings')
    check_in = models.DateField()
    check_out = models.DateField()
    adult_count = models.PositiveSmallIntegerField()
    children_count = models.PositiveSmallIntegerField(default=0)
    status = models.ForeignKey(BookingStatus, on_delete=models.PROTECT, related_name='bookings')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['check_in'] 
        unique_together = ('room', 'check_in', 'check_out')     
        
        
    def __str__(self):
        room_info = self.room.number if self.room else "No room assigned"
        return f"{room_info}: {self.check_in} - {self.check_out}"

    @property
    def number_of_guests(self):
        return self.adult_count + self.children_count


    @property
    def number_of_nights(self): 
        return (self.check_out - self.check_in).days if self.check_in and self.check_out else 0

    @property
    def total_cost(self):
        return self.room_type.price * self.number_of_nights if self.room_type else 0
    
    def clean(self):
        if self.check_in >= self.check_out:
            raise ValidationError("Check-in date must be before check-out date.")
        if self.number_of_guests > self.room_type.max_adult + (self.room_type.max_children or 0):
            raise ValidationError("Number of guests exceeds the allowed limit for this room type.")

    
    