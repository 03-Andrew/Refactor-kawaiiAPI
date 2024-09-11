from django.db import models
from django.db.models import Sum, F


# Create your models here.
class Customer(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    contact_number = models.CharField(max_length=11)
    email = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.last_name}, {self.first_name}"

class Transaction(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Transaction {self.id} for {self.customer}"

    def total_booking_cost(self):
        # Calculate total cost for all related bookings
        return sum(booking.total_cost for booking in self.booking_set.all())

    def total_food_bill(self):
        return sum(foodbill.price for foodbill in self.foodbill_set.all())
    
    def total_amenities(self):
        return self.amenitiesavailed_set.aggregate(
            total=Sum(F('head_count') * F('amenity__rate_per_head'))
        )['total'] or 0

    def total_activities(self):
        return self.activitiesavailed_set.aggregate(
            total=Sum(F('hours_availed') * F('activity__hourly_rate'))
        )['total'] or 0

    @property
    def total_cost(self):
        return self.total_booking_cost() + self.total_food_bill()  + self.total_amenities() + self.total_activities()
    
    @property
    def paid_amount(self):
        return sum(payment.amount for payment in self.payment_set.all())
    
    @property
    def running_balance(self):
        return self.total_cost - self.paid_amount

    @property
    def guests(self):
        # Get all guests from the GuestList associated with this transaction
        return [guest.guest for guest in self.guestlist_set.all()]
    
class GuestStatus(models.Model):
    status = models.CharField(max_length=100)
    
    def __str__(self):
        return self.status

class GuestList(models.Model):
    transaction = models.ForeignKey(Transaction, on_delete=models.PROTECT)
    guest = models.CharField(max_length=100)
    status = models.ForeignKey(GuestStatus, on_delete=models.PROTECT)
    
    def __str__(self):
        return f"{self.transaction.id} {self.guest}"
    
class FoodBill(models.Model):
    transaction = models.ForeignKey(Transaction, on_delete=models.SET_NULL, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    or_number = models.CharField(max_length=150, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.transaction.id} - {self.or_number}"
    
class Amenities(models.Model):
    amenity = models.CharField(max_length=100)
    rate_per_head = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.amenity}"

class AmenitiesAvailed(models.Model):
    transaction = models.ForeignKey(Transaction, on_delete=models.PROTECT)
    amenity = models.ForeignKey(Amenities, on_delete=models.PROTECT)
    head_count = models.SmallIntegerField()

    def __str__(self):
        return f"Amenities for Transaction {self.transaction.id}"
    
class Activity(models.Model):
    activity = models.CharField(max_length=100)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2)
    
    def __str__(self):
        return self.activity

class ActivitiesAvailed(models.Model):
    transaction = models.ForeignKey(Transaction, on_delete=models.PROTECT)
    activity = models.ForeignKey(Activity, on_delete=models.PROTECT)
    hours_availed = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    def __str__(self):
        return f"{self.transaction.id} {self.activity}"
 
class PaymentMethod(models.Model):
    mode = models.CharField(max_length=100)
    
    def __str__(self):
        return self.mode
    
class Payment(models.Model):
    transaction = models.ForeignKey(Transaction, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateTimeField()
    mop = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT)
    
    def __str__(self):
        return f"{self.transaction.id} {self.date}"