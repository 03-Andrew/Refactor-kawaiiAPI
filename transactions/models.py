from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey

# Create your models here.
class Customer(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    contact_number = models.CharField(max_length=11)
    email = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def __str__(self):
        return f"{self.last_name}, {self.first_name}"

class BillingStatus(models.TextChoices):
    PROCESSING = 'Processing', 'Processing'
    COMPLETE = 'Complete', 'Complete'
    PENDING = 'Pending', 'Pending'
    CANCELLED = 'Cancelled', 'Cancelled'

class Billing(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=BillingStatus.choices, default=BillingStatus.PROCESSING)
    
    def __str__(self):
        return f"Bill {self.id} for {self.customer}"

    def total_booking_cost(self):
        # Calculate total cost for all related bookings
        return sum(booking.total_cost for booking in self.bookings.all())

    def total_food_bill(self):
        return sum(f.price for f in self.food_bill.all())

    def total_amenities(self):
        return sum(a.head_count * a.amenity.rate_per_head for a in self.amenities_availed.all())

    def total_activities(self):
        return sum(a.hours_availed * a.activity.hourly_rate for a in self.activities_availed.all())

    def total_additional(self):
        return sum(a.price for a in self.additional_payment.all())
    
    @property
    def total_cost(self):
        # Aggregate the total cost by combining different totals
        return (self.total_booking_cost() + 
                self.total_food_bill() + 
                self.total_amenities() + 
                self.total_activities() + 
                self.total_additional())

    
    @property
    def paid_amount(self):
        return sum(payment.amount for payment in self.payment.all())
    
    @property
    def running_balance(self):
        return self.total_cost - self.paid_amount

    @property
    def guests(self):
        return [guest.guest for guest in self.guestlist_set.all()]
    
class GuestStatus(models.TextChoices):
    CHECKED_IN = 'CHECKED_IN', 'Checked In'
    CHECKED_OUT = 'CHECKED_OUT', 'Checked Out'
    PENDING = 'PENDING', 'Pending'
    

class GuestList(models.Model):
    customer_bill = models.ForeignKey(Billing, on_delete=models.PROTECT)
    guest = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=GuestStatus.choices, default=GuestStatus.PENDING)

    def __str__(self):
        return f"{self.customer_bill.id} {self.guest}"
    
class FoodBill(models.Model):
    customer_bill = models.ForeignKey(Billing, on_delete=models.SET_NULL, null=True, related_name="food_bill")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    or_number = models.CharField(max_length=150, null=True, blank=True)
    date = models.DateField(blank=True, null=True)
    time = models.TimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.customer_bill.id} - {self.or_number}"
    
class Amenities(models.Model):
    amenity = models.CharField(max_length=100)
    rate_per_head = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.amenity}"

class AmenitiesAvailed(models.Model):
    customer_bill = models.ForeignKey(Billing, on_delete=models.PROTECT, related_name="amenities_availed")
    amenity = models.ForeignKey(Amenities, on_delete=models.PROTECT, related_name="amenities_availed")
    head_count = models.SmallIntegerField()
    time = models.TimeField(null=True, blank=True, default="10:00")
    def __str__(self):
        return f"Amenities for bill {self.customer_bill.id}"
    
    @property
    def total_cost(self):
        return self.amenity.rate_per_head * self.head_count if self.amenity else 0
    
class Activity(models.Model):
    activity = models.CharField(max_length=100)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2)
    
    def __str__(self):
        return self.activity

class ActivitiesAvailed(models.Model):
    customer_bill = models.ForeignKey(Billing, on_delete=models.PROTECT, related_name="activities_availed")
    activity = models.ForeignKey(Activity, on_delete=models.PROTECT)
    hours_availed = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    def __str__(self):
        return f"{self.customer_bill.id} {self.activity}"
    
    @property
    def total_cost(self):
        return self.activity.hourly_rate * self.hours_availed if self.activity else 0


class ExtraItems(models.Model):
    item = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return self.item
    
class ExtraItemsAvailed(models.Model):
    customer_bill = models.ForeignKey(Billing, on_delete=models.CASCADE, related_name="extra_items")
    extraItem = models.ForeignKey(ExtraItems, on_delete=models.CASCADE, related_name="extra_items")
    count = models.SmallIntegerField()


class AdditonalPayment(models.Model):
    customer_bill = models.ForeignKey(Billing, on_delete=models.CASCADE, related_name="additional_payment")
    reason = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    
    def __str__(self):
        return f"Additonal payments for {self.customer_bill.id} - {self.customer_bill.customer.last_name}, {self.customer_bill.customer.first_name}"


class PaymentMethod(models.Model):
    mode = models.CharField(max_length=100)
    
    def __str__(self):
        return self.mode
    
class PaymentFor(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class PaymentStatus(models.Model):
    status = models.CharField(max_length=100)

    def __str__(self):
        return self.status
    
class Payment(models.Model):
    customer_bill = models.ForeignKey(Billing, on_delete=models.PROTECT, related_name="payment")
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    date = models.DateTimeField()
    mop = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT, related_name="payment")
    paymentFor = models.ForeignKey(PaymentFor, on_delete=models.PROTECT, null=True, blank=True, related_name="payment")
    status = models.ForeignKey(PaymentStatus, on_delete=models.PROTECT, null=True, blank=True, related_name="payment")

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    paid_for = GenericForeignKey('content_type', 'object_id')
    def __str__(self):
        return f"{self.customer_bill.id} {self.date}"
    
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
    