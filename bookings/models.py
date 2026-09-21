from django.db import models
from transactions.models import Billing
from django.core.exceptions import ValidationError
import random
# def generate_booking_ref():
#     allowed_chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890'
#     return ''.join(random.choices(allowed_chars, k=6))

class Inclusions(models.Model):
    inclusion = models.CharField(max_length=100)

    def __str__(self):
        return self.inclusion


class RoomType(models.Model):
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(null=True, blank=True)
    good_for = models.PositiveSmallIntegerField(default=2)
    max_extra_guest = models.PositiveSmallIntegerField(default=1)
    inclusions = models.ManyToManyField(Inclusions)

    def __str__(self):
        return self.name
    
class RoomStatus(models.TextChoices):
    AVAILABLE = 'AVAILABLE', 'Available'
    MAINTENANCE = 'MAINTENANCE', 'Maintenance'


class Room(models.Model):
    number = models.CharField(max_length=100, unique=True)
    type = models.ForeignKey(RoomType, on_delete=models.PROTECT, related_name="room")
    status = models.CharField(max_length=20, choices=RoomStatus.choices, default=RoomStatus.AVAILABLE)

    def __str__(self):
        return f"Room {self.number} - {self.type.name}"


class BookingStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'
    CANCELLED = 'CANCELLED', 'Cancelled'

class Booking(models.Model):
    customer_bill = models.ForeignKey(Billing, on_delete=models.PROTECT,  related_name='bookings')
    # reference_id = models.CharField(max_length=8, unique=True, db_index=True, editable=False)
    room = models.ForeignKey(Room, on_delete=models.PROTECT, null=True, blank=True, related_name='bookings')
    room_type = models.ForeignKey(RoomType, on_delete=models.PROTECT, related_name='bookings')
    check_in = models.DateField()
    check_out = models.DateField()
    adult_count = models.PositiveSmallIntegerField()
    children_count = models.PositiveSmallIntegerField(default=0)
    extra_guest =  models.PositiveSmallIntegerField(null=True, blank=True, default=0)
    status = models.CharField(max_length=20, choices=BookingStatus.choices, default=BookingStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['check_in'] 
        unique_together = ('room', 'check_in', 'check_out')     
        
        
    def __str__(self):
        room_info = self.room.number if self.room else "No room assigned"
        return f"{room_info}: {self.check_in} - {self.check_out}"

    @property
    def number_of_guests(self):
        return self.adult_count + self.children_count + (self.extra_guest or 0)


    @property
    def number_of_nights(self): 
        return (self.check_out - self.check_in).days if self.check_in and self.check_out else 0

    @property
    def total_cost(self):
        base_cost = self.room_type.price * self.number_of_nights if self.room_type else 0
        extra_guest_cost = 1500 * self.extra_guest * self.number_of_nights if self.extra_guest else 0
        return base_cost + extra_guest_cost
    
    def clean(self):
        if self.check_in >= self.check_out:
            raise ValidationError("Check-in date must be before check-out date.")
        if self.number_of_guests > self.room_type.good_for + self.room_type.max_exta_guest:
            raise ValidationError("Number of guests exceeds the allowed limit for this room type.")

    # def save(self, *args, **kwargs):
    #     if not self.reference_id:
    #         self.reference_id = generate_booking_ref()

    #         while Booking.objects.filter(reference_id=self.reference_id).exists():
    #             self.reference_id = generate_booking_ref()

    #     super().save(*args,**kwargs)


    
    