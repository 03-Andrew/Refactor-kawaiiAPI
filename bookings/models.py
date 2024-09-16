from django.db import models
from transactions.models import Transaction

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
    number = models.CharField(max_length=100)
    type = models.ForeignKey(RoomType, on_delete=models.PROTECT)
    status = models.ForeignKey(RoomStatus, on_delete=models.PROTECT)
    

    def __str__(self):
        return f"Room {self.number} - {self.type.name}"


class BookingStatus(models.Model):
    name = models.CharField(max_length=50, null=True)

    def __str__(self):
        return self.name

class Booking(models.Model):
    transaction = models.ForeignKey(Transaction, on_delete=models.PROTECT)
    room = models.ForeignKey(Room, on_delete=models.PROTECT, null=True, blank=True)
    room_type = models.ForeignKey(RoomType, on_delete=models.PROTECT)
    check_in = models.DateField()
    check_out = models.DateField()
    number_of_guests = models.PositiveSmallIntegerField()
    status = models.ForeignKey(BookingStatus, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        room_info = self.room.number if self.room else "No room assigned"
        return f"{room_info}: {self.check_in} - {self.check_out}"

    @property
    def number_of_nights(self):
        return (self.check_out - self.check_in).days

    @property
    def total_cost(self):
        # Implement the logic to calculate the total cost for this specific booking
        # Example: return self.room_type.price * self.number_of_nights
        return self.room_type.price * self.number_of_nights if self.room_type else 0

    
    