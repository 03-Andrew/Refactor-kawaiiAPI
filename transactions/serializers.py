from rest_framework import serializers

from bookings.models import Booking
from .models import FoodBill, AdditonalPayment, Billing, Customer, Payment, GuestList ,Amenities, AmenitiesAvailed, Activity, ActivitiesAvailed, Food, PaymentForChoices
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

class AmenitiesAvailedNestedSerializer(serializers.ModelSerializer):
    amenity = AmenitiesSerializer()
    class Meta:
        model = AmenitiesAvailed
        fields = ['id', 'head_count', 'amenity']


class FoodBillSerializer(serializers.ModelSerializer):
    class Meta:
        model = FoodBill
        fields = '__all__'

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
        return obj.paymentFor
    
    def get_object_name(self, obj):
        if not obj.paymentFor or not obj.object_id:
            return None

        if obj.paymentFor == PaymentForChoices.FOOD:
            foodBill = FoodBill.objects.filter(id=obj.object_id).first()
            if foodBill:
                return f"Food Bill #{foodBill.or_number}"

        elif obj.paymentFor == PaymentForChoices.ROOM:
            booking = Booking.objects.filter(id=obj.object_id).first()
            if booking and booking.room:
                return str(booking.room)

        elif obj.paymentFor == PaymentForChoices.AMENITIES:
            amenities = AmenitiesAvailed.objects.filter(id=obj.object_id).first()
            if amenities and amenities.amenity:
                return str(amenities.amenity)

        elif obj.paymentFor == PaymentForChoices.ACTIVITIES:
            activities = ActivitiesAvailed.objects.filter(id=obj.object_id).first()
            if activities and activities.activity:
                return str(activities.activity)

        elif obj.paymentFor == PaymentForChoices.ADDITIONAL:
            additional = AdditonalPayment.objects.filter(id=obj.object_id).first()
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


# ── CreatePayment request serializers ────────────────────────────

class PaymentItemSerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1)
    price = serializers.DecimalField(max_digits=20, decimal_places=2, required=False)
    subtotal = serializers.DecimalField(max_digits=20, decimal_places=2, required=False)

    def get_amount(self):
        return self.validated_data.get("price") or self.validated_data.get("subtotal", 0)


class SelectedItemsSerializer(serializers.Serializer):
    selectedRooms = PaymentItemSerializer(many=True, required=False, default=list)
    selectedActivities = PaymentItemSerializer(many=True, required=False, default=list)
    selectedAmenities = PaymentItemSerializer(many=True, required=False, default=list)
    selectedFoodBills = PaymentItemSerializer(many=True, required=False, default=list)
    selectedAdditionalPayments = PaymentItemSerializer(many=True, required=False, default=list)


class CustomerInfoSerializer(serializers.Serializer):
    customer_bill = serializers.IntegerField(min_value=1)
    date = serializers.DateField()
    mop = serializers.IntegerField(min_value=1)
    status = serializers.IntegerField(min_value=1)


class CreatePaymentSerializer(serializers.Serializer):
    customerInfo = CustomerInfoSerializer()
    amount = serializers.DecimalField(max_digits=20, decimal_places=2, default=0)
    selectedItems = SelectedItemsSerializer()

    def create(self, validated_data):
        from django.contrib.contenttypes.models import ContentType
        from django.utils.timezone import make_aware
        from datetime import datetime

        customer_info = validated_data["customerInfo"]
        selected_items = validated_data["selectedItems"]

        customer_bill_id = customer_info["customer_bill"]
        date = make_aware(datetime.combine(customer_info["date"], datetime.min.time()))
        mop_id = customer_info["mop"]
        status_id = customer_info["status"]

        item_mapping = {
            "selectedRooms": (Booking, "Room"),
            "selectedActivities": (ActivitiesAvailed, "Activities"),
            "selectedAmenities": (AmenitiesAvailed, "Amenities"),
            "selectedFoodBills": (FoodBill, "Food"),
            "selectedAdditionalPayments": (AdditonalPayment, "Additional"),
        }

        created_payments = []

        for key, (model, payment_for) in item_mapping.items():
            items = selected_items.get(key, [])
            if not items:
                continue

            content_type = ContentType.objects.get_for_model(model)

            for item in items:
                amount = item.get("price") or item.get("subtotal", 0)
                payment_data = {
                    "customer_bill": customer_bill_id,
                    "amount": amount,
                    "date": date,
                    "mop": mop_id,
                    "paymentFor": payment_for,
                    "status": status_id,
                    "content_type": content_type.id,
                    "object_id": item["id"],
                }
                payment_serializer = PaymentBaseSerializer(data=payment_data)
                payment_serializer.is_valid(raise_exception=True)
                payment = payment_serializer.save()
                created_payments.append(payment_serializer.data)

        return created_payments
    