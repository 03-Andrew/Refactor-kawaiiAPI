from django.db import models
from transactions.models import Billing


# Create your models here.
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
    customer_bill = models.ForeignKey(Billing, on_delete=models.PROTECT, related_name='payment')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateTimeField()
    mop = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT)
    paymentFor = models.ForeignKey(PaymentFor, on_delete=models.PROTECT)
    status = models.ForeignKey(PaymentStatus, on_delete=models.PROTECT)

    def __str__(self):
        return f"{self.customer_bill.id} {self.date}"