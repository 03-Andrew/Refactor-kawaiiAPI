from django.db import models

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
    guest_list = models.JSONField(default=list)  # Assuming this is added for the list of guest names

    def __str__(self):
        return f"Transaction {self.id} for {self.customer}"

    def total_booking_cost(self):
        # Calculate total cost for all related bookings
        return sum(booking.total_cost for booking in self.booking_set.all())

    def total_food_bill(self):
        return sum(foodbill.price for foodbill in self.foodbill_set.all())
    
    def subtotal_amenities(self):
        total = 0
        amenities_availed = AmenitiesAvailed.objects.filter(transaction=self)
        for item in amenities_availed:
            total += item.head_count * item.amenity.rate_per_head
        return total

    @property
    def total_cost(self):
        return self.total_booking_cost() + self.total_food_bill()  + self.subtotal_amenities()

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
    


    