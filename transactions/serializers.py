from rest_framework import serializers

from bookings.models import Booking
from .models import FoodBill, AdditonalPayment, Billing, Customer, Payment, GuestList ,Amenities, AmenitiesAvailed, Activity, ActivitiesAvailed, PaymentFor, Food
from bookings.serializers import BookingSerializer

class ActivitiesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Activity
        fields = '__all__'

class ActivitiesAvailedSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivitiesAvailed
        fields = '__all__'

class ActivitiesAvailedNestedSerializer(serializers.ModelSerializer):
    activity = ActivitiesSerializer()
    class Meta:
        model = ActivitiesAvailed
        fields = ['id', 'hours_availed', 'activity']

class AmenitiesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Amenities
        fields = '__all__'

class AmenitiesAvailedSerializer(serializers.ModelSerializer):
    class Meta:
        model = AmenitiesAvailed
        fields = '__all__'

# Dupe
class AmenitiesAvailedNestedSerializer(serializers.ModelSerializer):
    amenity = AmenitiesSerializer()
    class Meta:
        model = AmenitiesAvailed
        fields = ['id', 'head_count', 'amenity']


class FoodBillSerializer(serializers.ModelSerializer):
    class Meta:
        model = FoodBill
        fields = '__all__'

# Dupe
class FoodBillSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = FoodBill
        fields = ['id', 'price', 'or_number']

class AdditionalPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdditonalPayment
        fields = '__all__'

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = '__all__'


class BillingSerializerBase(serializers.ModelSerializer):
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

class PaymentBaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = "__all__"

class GuestListSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuestList
        fields = ['id', 'customer_bill', 'guest', 'status']

class PaymentDetailSerializer(serializers.ModelSerializer):
    content_type = serializers.SerializerMethodField()
    object_name = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = '__all__'

    def get_content_type(self, obj):
        if obj.content_type:
            return obj.content_type.model  
        return None 
    
    def get_object_name(self, obj):
        if obj.content_type and obj.object_id:
            if obj.content_type.model == 'foodbill':
                foodBill = FoodBill.objects.filter(id=obj.object_id).first()
                if foodBill:
                    formatted_time = foodBill.time.strftime("%I:%M %p") if foodBill.time else "N/A"

                    return f"Food Bill #{str(foodBill.or_number)}"
            
            elif obj.content_type.model == 'booking':
                booking = Booking.objects.filter(id=obj.object_id).first()
                if booking and booking.room:
                    return str(booking.room) 
            elif obj.content_type.model == 'amenitiesavailed':
                amenities = AmenitiesAvailed.objects.filter(id=obj.object_id).first()
                if amenities and amenities.amenity:
                    return str(amenities.amenity) 
            elif obj.content_type.model == 'activitiesavailed':
                activities = ActivitiesAvailed.objects.filter(id=obj.object_id).first()
                if activities and activities.activity:
                    return str(activities.activity) 
            elif obj.content_type.model == 'additonalpayment':
                additional = AdditonalPayment.objects.filter(id=obj.object_id).first()
                print("HEYEYE", additional)
                if additional:
                    return str(additional.reason)
        return None 

class BillingDetailSerializer(serializers.ModelSerializer):
    customer = CustomerSerializer()
    booking = BookingSerializer(many=True, read_only=True, source='bookings')
    payments = PaymentDetailSerializer(many=True, read_only=True, source='payment')
    amenitiesAvailed = AmenitiesAvailedNestedSerializer(many=True, read_only=True, source="amenities_availed")
    activitiesAvailed = ActivitiesAvailedNestedSerializer(many=True, read_only=True, source="activities_availed")
    foodBill = FoodBillSummarySerializer(many=True, read_only=True, source="food_bill")
    additionalPayment = AdditionalPaymentSerializer(many=True, read_only=True, source='additional_payment')
    bookingTotal = serializers.SerializerMethodField()
    amenityTotal = serializers.SerializerMethodField()
    activityTotal = serializers.SerializerMethodField()
    foodBillTotal = serializers.SerializerMethodField()
    additionalPaymentTotal = serializers.SerializerMethodField()
    runningBalance = serializers.SerializerMethodField()
    paidAmount = serializers.SerializerMethodField()

    class Meta:
        model = Billing
        fields = [
            'id', 'customer', 'booking', 'bookingTotal', 
            'amenitiesAvailed', 'amenityTotal', 'activitiesAvailed', 
            'activityTotal', 'foodBill', 'foodBillTotal', 
            'additionalPayment', 'additionalPaymentTotal', 
            'total_cost', 'runningBalance', 'paidAmount', 'payments'
        ] 
        
    def get_bookingTotal(self, obj):
        return obj.total_booking_cost()

    def get_amenityTotal(self, obj):
        return obj.total_amenities()
    
    def get_activityTotal(self, obj):
        return obj.total_activities()

    def get_foodBillTotal(self, obj):
        return obj.total_food_bill()
    
    def get_additionalPaymentTotal(self, obj):  
        return obj.total_additional()
    
    def get_paidAmount(self, obj):
        return obj.paid_amount 
    
    def get_runningBalance(self, obj):
        return obj.running_balance 
    
class FoodListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Food
        fields = '__all__'
    