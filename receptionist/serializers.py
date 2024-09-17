from rest_framework.serializers import ModelSerializer,IntegerField, CharField, DateField, StringRelatedField, SerializerMethodField
from bookings.models import Booking, BookingStatus, Room
from transactions.models import Transaction, Payment, Amenities, AmenitiesAvailed, Activity, ActivitiesAvailed, Customer
from datetime import date
from django.db.models.functions import TruncDate


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

class PaymentSerializer(ModelSerializer):
    class Meta:
        model = Payment
        fields = '__all__'

class CustomerSerializer(ModelSerializer):
    class Meta:
        model = Customer
        fields = '__all__'

class TransactionSerializer(ModelSerializer):
    customer = CustomerSerializer()
    class Meta:
        model = Transaction
        fields = '__all__'

class BookingsSerializer(ModelSerializer):
    class Meta:
        model = Booking
        fields = '__all__'

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

class AmenitiesAvailedSerializer(ModelSerializer):
    class Meta:
        model = AmenitiesAvailed
        fields = '__all__'

class BookingsListSerializer(ModelSerializer):
    transaction=TransactionSerializer()
    room_info = StringRelatedField(source='__str__', read_only=True)
    number_of_nights = SerializerMethodField()
    total_cost = SerializerMethodField()
    downpayment= SerializerMethodField()
    status = BookingStatusSerializer()
    room = RoomSerializer()
    room_type = RoomTypeSerializer()

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
            'transaction',
            'created_at'
        ]

    def get_downpayment(self, obj):
         # Get the first payment record with the same date as the booking's created_at (temporary?)
        downpayment = Payment.objects.filter(date__date=TruncDate(obj.created_at)).order_by('date').first()
        if downpayment:
            return PaymentSerializer(downpayment).data
        return None

    def get_total_cost(self, obj):
        return obj.total_cost

    def get_number_of_nights(self, obj):
        return obj.number_of_nights
    
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
    transaction = TransactionSerializer()
    amenity= AmenitiesSerializer()
    total_cost = SerializerMethodField()

    class Meta:
        model = AmenitiesAvailed
        fields = [
            'id',
            'total_cost',
            'head_count',
            'amenity',
            'transaction',
        ]
    
    def get_total_cost(self, obj):
        return obj.total_cost
    
class ActivitiesAvailedListSerializer(ModelSerializer):
    transaction = TransactionSerializer()
    activity = ActivitiesSerializer()
    total_cost = SerializerMethodField()
    
    class Meta:
        model = ActivitiesAvailed
        fields = [
            'id',
            'total_cost',
            'hours_availed',
            'activity',
            'transaction',
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