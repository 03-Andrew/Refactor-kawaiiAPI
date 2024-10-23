from rest_framework import serializers
from .models import Billing, Customer, Payment, GuestList,GuestStatus ,Amenities, AmenitiesAvailed, Activity, ActivitiesAvailed, PaymentFor, BillingStatus

from bookings.models import Booking

from django.db.models import Sum, F

from receptionist.serializers import ActivitiesAvailedSerializer2, AmenitiesAvailedSerializer2, FoodBillSerializer2, AdditionalPaymentSerializer


from bookings.serializers import BookingSerializer

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = '__all__'

class CustomerSerializer2(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ['first_name', 'last_name']

class BillingSerialzerBase(serializers.ModelSerializer):
    class Meta:
        model = Billing
        fields = "__all__"

class BillingSerializer(serializers.ModelSerializer):
    total_cost = serializers.SerializerMethodField()
    paid_amount = serializers.SerializerMethodField()
    running_balance = serializers.SerializerMethodField()
    customer = CustomerSerializer()
    
    class Meta:
        model = Billing
        fields = "__all__"

    def get_total_cost(self, obj):
        return obj.total_cost or 0

    def get_paid_amount(self, obj):
        return obj.paid_amount or 0

    def get_running_balance(self, obj):
        return obj.running_balance or 0



class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = "__all__"

class GuestStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuestStatus
        fields = ['id','status']

class GuestListSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuestList
        fields = ['id', 'guest', 'status']
        
class GuestListSerializerAll(serializers.ModelSerializer):
    status = GuestStatusSerializer()
    class Meta:
        model = GuestList
        fields = ['id', 'customer_bill', 'guest', 'status']

class BillingGuestList(serializers.ModelSerializer):
    guests_list = serializers.SerializerMethodField()

    class Meta:
        model = Billing
        fields = ['id', 'customer', 'guests_list']

    def get_guests_list(self, obj):
        # Fetch and serialize the guest list associated with this Billing
        guest_list = GuestList.objects.filter(customer_bill=obj)
        return GuestListSerializer(guest_list, many=True).data

class BillingStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillingStatus
        fields = ['status']

class ConfirmedBooking(BookingSerializer):
    availed_boat_transfer = serializers.SerializerMethodField()
    room_type = serializers.CharField(source='room_type.name')

    class Meta:
        model = Booking
        fields = '__all__'
    
    def get_availed_boat_transfer(self, obj):
    # Get the AmenitiesAvailed object with 'boat transfer' amenity
        boat_transfer = AmenitiesAvailed.objects.filter(
            customer_bill=obj.customer_bill, amenity__amenity='boat transfer'
        ).first()
        
        # If the boat transfer exists, return the time; otherwise return None
        return boat_transfer.time if boat_transfer else "Not Availed"

class PendingBookings(serializers.ModelSerializer):
    customer = CustomerSerializer()
    booking = BookingSerializer(many=True, read_only=True, source='bookings')
    availed_boat_transfer = serializers.SerializerMethodField()
    booking_payment = serializers.SerializerMethodField()
    total_booking_bill = serializers.SerializerMethodField()
    status = BillingStatusSerializer()
    total_guests = serializers.SerializerMethodField()
    class Meta:
        model = Billing
        fields = ['id', 'customer', 'booking', 'total_guests','total_booking_bill', 'availed_boat_transfer', 'booking_payment', 'status']

    
    def get_availed_boat_transfer(self, obj):
    # Get the AmenitiesAvailed object with 'boat transfer' amenity
        boat_transfer = AmenitiesAvailed.objects.filter(
            customer_bill=obj, amenity__amenity='boat transfer'
        ).first()
        
        # If the boat transfer exists, return the time; otherwise return None
        return boat_transfer.time if boat_transfer else "Not Availed"

    def get_booking_payment(self, obj):
        # Get the 'Down Payment' PaymentFor instance
        downpayment_payment_for = PaymentFor.objects.filter(name__iexact='Down Payment').first()

        if downpayment_payment_for:
            # Retrieve the first Payment linked to this Billing that is for down payment
            payment = obj.payment.filter(paymentFor=downpayment_payment_for).first()  
            
            if payment:
                return {
                    "amount": payment.amount,  # Convert amount to string if needed
                    "mode_of_payment": payment.mop.mode  # Return the mode of payment
                }
        
        return {
            "amount": 0,  # Convert amount to string if needed
            "mode_of_payment": None  # Return the mode of payment
        }
    
    def get_total_booking_bill(self, obj):
        # Utilize the existing total_booking_cost method
        return obj.total_booking_cost()
    
    def get_total_guests(self, obj):
        bookingss = obj.bookings.all()  # Use related_name if it's set
        return sum(booking.number_of_guests for booking in bookingss)




class BillingDetailSerializer(serializers.ModelSerializer):
    customer = CustomerSerializer()
    booking  =  BookingSerializer(many=True, read_only=True, source='bookings')
    amenitiesAvailed = AmenitiesAvailedSerializer2(many=True, read_only=True, source="amenities_availed")
    activitiesAvailed = ActivitiesAvailedSerializer2(many=True, read_only=True, source="activities_availed")
    foodBill = FoodBillSerializer2(many=True, read_only=True, source="food_bill")
    additonalPayment = AdditionalPaymentSerializer(many=True, read_only=True, source='additional_payment')
    bookingTotal = serializers.SerializerMethodField()
    amenityTotal = serializers.SerializerMethodField()
    activityTotal = serializers.SerializerMethodField()
    foodBillTotal = serializers.SerializerMethodField()
    additionalPaymentTotal = serializers.SerializerMethodField()
    class Meta:
        model = Billing
        fields = ['id', 'customer','booking','bookingTotal','amenitiesAvailed','amenityTotal','activitiesAvailed','activityTotal','foodBill','foodBillTotal', 'additonalPayment','additionalPaymentTotal','total_cost'] 
        
    def get_bookingTotal(self, obj):
        return obj.total_booking_cost()

    def get_amenityTotal(self, obj):
        return obj.total_amenities()
    
    def get_activityTotal(self, obj):
        return obj.total_activities()

    def get_foodBillTotal(self, obj):
        return obj.total_food_bill()
    
    def get_additionalPaymentTotal(slef, obj):
        return obj.total_additional()
    
    
    
    