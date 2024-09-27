from rest_framework import serializers
from .models import Transaction, Customer, Payment, GuestList,GuestStatus ,Amenities, AmenitiesAvailed, Activity, ActivitiesAvailed, PaymentFor

from django.db.models import Sum, F


from bookings.serializers import BookingSerializer2

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ['first_name', 'last_name']

class TransactionSerialzerBase(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = "__all__"

class TransactionSerializer(serializers.ModelSerializer):
    total_cost = serializers.SerializerMethodField()
    paid_amount = serializers.SerializerMethodField()
    running_balance = serializers.SerializerMethodField()
    customer = CustomerSerializer()
    
    class Meta:
        model = Transaction
        fields = "__all__"

    def get_total_cost(self, obj):
        return obj.total_cost or 0

    def get_paid_amount(self, obj):
        return obj.paid_amount or 0

    def get_running_balance(self, obj):
        return obj.running_balance or 0



class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = "__all__"


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = "__all__"

class GuestStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuestStatus
        fields = "__all__"

class GuestListSerializer(serializers.ModelSerializer):
    status = GuestStatusSerializer
    class Meta:
        model = GuestList
        fields = ['id', 'guest', 'status']

class TransactionGuestList(serializers.ModelSerializer):
    guests_list = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = ['id', 'customer', 'guests_list']

    def get_guests_list(self, obj):
        # Fetch and serialize the guest list associated with this transaction
        guest_list = GuestList.objects.filter(transaction=obj)
        return GuestListSerializer(guest_list, many=True).data



class ApproveBookings(serializers.ModelSerializer):
    customer_name = serializers.SerializerMethodField()
    bookings = BookingSerializer2(many=True, read_only=True, source='booking_set')
    availed_boat_transfer = serializers.SerializerMethodField()
    booking_payment = serializers.SerializerMethodField()
    total_booking_bill = serializers.SerializerMethodField()


    class Meta:
        model = Transaction
        fields = ['id', 'customer_name', 'bookings', 'total_booking_bill', 'availed_boat_transfer', 'booking_payment']

    def get_customer_name(self, obj):
        return f"{obj.customer.first_name} {obj.customer.last_name}"
    
    def get_availed_boat_transfer(self, obj):
        # Check if any of the amenities availed for this transaction is 'Boat Transfer'
        return AmenitiesAvailed.objects.filter(transaction=obj, amenity__amenity='boat transfer').exists()

    def get_booking_payment(self, obj):
        # Get the 'Down Payment' PaymentFor instance
        downpayment_payment_for = PaymentFor.objects.filter(name__iexact='Down Payment').first()

        if downpayment_payment_for:
            # Retrieve the first Payment linked to this transaction that is for down payment
            payment = obj.payment_set.filter(paymentFor=downpayment_payment_for).first()  
            
            if payment:
                return {
                    "amount": str(payment.amount),  # Convert amount to string if needed
                    "mode_of_payment": payment.mop.mode  # Return the mode of payment
                }
        
        return None
    
    def get_total_booking_bill(self, obj):
        # Utilize the existing total_booking_cost method
        return obj.total_booking_cost()
    

    