from django.db.models.functions import TruncDate
from rest_framework.serializers import ModelSerializer,IntegerField, CharField, StringRelatedField, SerializerMethodField
from datetime import date

from bookings.models import Booking, Room
from transactions.models import Payment, AmenitiesAvailed, ActivitiesAvailed, FoodBill
from transactions.serializers import AmenitiesAvailedNestedSerializer, BillingSerializer, ActivitiesSerializer, AmenitiesSerializer, ActivitiesAvailedNestedSerializer, FoodBillSummarySerializer
from bookings.serializers import RoomSerializer ,BookingCountSerializer


class BookingsListSerializer(ModelSerializer):
    customer_bill=BillingSerializer()
    room_info = StringRelatedField(source='__str__', read_only=True)
    number_of_nights = SerializerMethodField()
    total_cost = SerializerMethodField()
    downpayment= SerializerMethodField()
    status = CharField(source='status.name', read_only=True)
    room = RoomSerializer()


    def get_downpayment(self, obj):
         # Get the first payment record with the same date as the booking's created_at (temporary?)
        downpayment = Payment.objects.filter(date__date=TruncDate(obj.created_at)).order_by('date').first()
        if downpayment:
            return PaymentSerializer(downpayment).data
        return 0

    def get_total_cost(self, obj):
        return obj.total_cost

    def get_number_of_nights(self, obj):
        return obj.number_of_nights
    

    class Meta:
        model = Booking
        fields = [
            'id',
            'check_in',
            'check_out',
            'number_of_nights',
            'number_of_guests',
            'total_cost',
            'room_info',
            'room',
            'room_type',
            'downpayment',
            'status',
            'customer_bill',
            'created_at'
        ]

class RoomBookingListSerializer(ModelSerializer):
    today_booking = SerializerMethodField()

    class Meta:
        model = Room
        fields = '__all__'

    def get_today_booking(self, obj):
        # Get today's booking, if none then null
        today_booking = Booking.objects.filter(room=obj, check_in__lte=date.today(), check_out__gte=date.today()).order_by('check_in').first()
        if today_booking:
            return BookingsListSerializer(today_booking).data
        return None
    
class AmenitiesAvailedListSerializer(ModelSerializer):
    customer_bill = BillingSerializer()
    amenity= AmenitiesSerializer()
    total_cost = SerializerMethodField()

    class Meta:
        model = AmenitiesAvailed
        fields = [
            'id',
            'total_cost',
            'head_count',
            'amenity',
            'customer_bill',
        ]
    
    def get_total_cost(self, obj):
        return obj.total_cost
    
class ActivitiesAvailedListSerializer(ModelSerializer):
    customer_bill = BillingSerializer()
    activity = ActivitiesSerializer()
    total_cost = SerializerMethodField()
    
    class Meta:
        model = ActivitiesAvailed
        fields = [
            'id',
            'total_cost',
            'hours_availed',
            'activity',
            'customer_bill',
        ]
    
    def get_total_cost(self, obj):
        return obj.total_cost
      
class PaymentSerializer(ModelSerializer):
    paid_for = SerializerMethodField()
    paymentFor = CharField(source="get_paymentFor_display")
    mop = CharField(source="mop.mode")
    customer_bill = SerializerMethodField()
    class Meta:
        model = Payment
        fields = '__all__'
    
    def get_paid_for(self, obj):
        paid_for = getattr(obj, '_cached_paid_for', None) or obj.paid_for
        if paid_for is None:
            return None
        if isinstance(paid_for, Booking):
            return BookingCountSerializer(paid_for).data
        elif isinstance(paid_for, AmenitiesAvailed):
            return AmenitiesAvailedNestedSerializer(paid_for).data
        elif isinstance(paid_for, ActivitiesAvailed):
            return ActivitiesAvailedNestedSerializer(paid_for).data
        elif isinstance(paid_for, FoodBill):
            return FoodBillSummarySerializer(paid_for).data
        else:
            return None
        
    def get_customer_bill(self, obj):
        return f"{obj.customer_bill.customer.last_name}, {obj.customer_bill.customer.first_name}"