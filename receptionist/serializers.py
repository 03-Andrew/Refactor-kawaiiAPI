from rest_framework.serializers import ModelSerializer,IntegerField, CharField, DateField, StringRelatedField, SerializerMethodField
from bookings.models import Booking, BookingStatus, Room
from transactions.models import Billing, Payment, Amenities, AmenitiesAvailed, Activity, ActivitiesAvailed, Customer, FoodBill, AdditonalPayment
from datetime import date
from django.db.models.functions import TruncDate



class CustomerSerializer2(ModelSerializer):
    class Meta:
        model = Customer
        fields = ['first_name', 'last_name']

class BillingSerializer(ModelSerializer):
    customer = CustomerSerializer2()
    
    class Meta:
        model = Billing
        fields = ['customer']


class BookingStatusSerializer(ModelSerializer):
    class Meta:
        model = BookingStatus
        fields = '__all__'

class RoomTypeSerializer(ModelSerializer):
    class Meta:
        model = BookingStatus
        fields = '__all__'

class RoomSerializer(ModelSerializer):
    type = RoomTypeSerializer()
    class Meta:
        model = Room
        fields = '__all__'

class RoomStatusSerializer(ModelSerializer):
    class Meta:
        model = Room
        fields = '__all__'

class CustomerSerializer(ModelSerializer):
    class Meta:
        model = Customer
        fields = '__all__'

class BillingSerializer(ModelSerializer):
    customer = CustomerSerializer()
    class Meta:
        model = Billing
        fields = '__all__'

class BookingsSerializer(ModelSerializer):
    class Meta:
        model = Booking
        fields = '__all__'

class BookingsSerializer2(ModelSerializer):
    class Meta:
        model = Booking
        fields = ['room']

class AmenitiesSerializer(ModelSerializer):
    class Meta:
        model = Amenities
        fields = '__all__'

class ActivitiesSerializer(ModelSerializer):
    class Meta:
        model = Activity
        fields = '__all__'
   
   
class ActivitiesAvailedSerializer(ModelSerializer):
    class Meta:
        model = ActivitiesAvailed
        fields = '__all__'
    
class ActivitiesAvailedSerializer2(ModelSerializer):
    activity = ActivitiesSerializer()
    class Meta:
        model = ActivitiesAvailed
        fields = ['id', 'hours_availed', 'activity']
    
class AmenitiesAvailedSerializer(ModelSerializer):
    class Meta:
        model = AmenitiesAvailed
        fields = '__all__'
        
class AmenitiesAvailedSerializer2(ModelSerializer):
    amenity = AmenitiesSerializer()
    class Meta:
        model = AmenitiesAvailed
        fields = ['id', 'head_count', 'amenity']

class FoodBillSerializer(ModelSerializer):
    class Meta:
        model = FoodBill
        fields = '__all__'
        
class FoodBillSerializer2(ModelSerializer):
    class Meta:
        model = FoodBill
        fields = ['id', 'price', 'or_number']
        


class AdditionalPaymentSerializer(ModelSerializer):
    class Meta:
        model = AdditonalPayment
        fields = ['id', 'reason','price']

class BookingsListSerializer(ModelSerializer):
    customer_bill=BillingSerializer()
    room_info = StringRelatedField(source='__str__', read_only=True)
    number_of_nights = SerializerMethodField()
    total_cost = SerializerMethodField()
    downpayment= SerializerMethodField()
    status = BookingStatusSerializer()
    room = RoomSerializer()
    room_type = RoomTypeSerializer()


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
    
class RoomStatusListSerializer(ModelSerializer):
    room_type = CharField(source='type.name')
    max_adult = IntegerField(source='type.max_adult')
    max_children = IntegerField(source='type.max_children')
    room_status = CharField(source='status.name')
    check_out = SerializerMethodField()

    class Meta:
        model = Room
        fields = '__all__'

    def get_check_out(self, obj):
    # Get today's check out (if there is)
        today_booking = Booking.objects.filter(room=obj, check_in__lte=date.today(), check_out__gte=date.today()).order_by('check_in').first()
        return today_booking.check_out if today_booking else None
    


class PaymentSerializer(ModelSerializer):
    paid_for = SerializerMethodField()
    paymentFor = CharField(source="paymentFor.name")
    mop = CharField(source="mop.mode")
    customer_bill = SerializerMethodField()
    class Meta:
        model = Payment
        fields = '__all__'
    
    def get_paid_for(self, obj):
        if isinstance(obj.paid_for, Booking):
            return BookingsSerializer2(obj.paid_for).data
        elif isinstance(obj.paid_for, AmenitiesAvailed):
            return AmenitiesAvailedSerializer2(obj.paid_for).data
        elif isinstance(obj.paid_for, ActivitiesAvailed):
            return ActivitiesAvailedSerializer2(obj.paid_for).data
        elif isinstance(obj.paid_for, FoodBill):
            return FoodBillSerializer2(obj.paid_for).data
        else:
            return None
        
    def get_customer_bill(self, obj):
        return f"{obj.customer_bill.customer.last_name}, {obj.customer_bill.customer.first_name}"