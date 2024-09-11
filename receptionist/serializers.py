from rest_framework.serializers import ModelSerializer,IntegerField, CharField, DateField, StringRelatedField, SerializerMethodField
from bookings.models import Booking, Room
from transactions.models import Payment
from datetime import date
from django.db.models.functions import TruncDate

class PendingBookingsSerializer(ModelSerializer):
    class Meta:
        model = Booking
        fields = '__all__'

class PendingBookingsListSerializer(ModelSerializer):
    transaction_name = StringRelatedField(source='transaction.customer')
    downpayment = SerializerMethodField()
    room_info = StringRelatedField(source='__str__', read_only=True)
    number_of_nights = SerializerMethodField()
    total_cost = SerializerMethodField()


    class Meta:
        model = Booking
        fields = '__all__'

    def get_downpayment(self, obj): 
        # Get the first payment record with the same date as the booking's created_at (temporary?)
        downpayment = Payment.objects.filter(date__date=TruncDate(obj.created_at)).order_by('date').first()
        return downpayment.amount if downpayment else None
    
    def get_total_cost(self, obj):
        return obj.total_cost
    
    def get_number_of_nights(self, obj):
        return obj.number_of_nights
    
class RoomStatusSerializer(ModelSerializer):
    class Meta:
        model = Room
        fields = '__all__'

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

class RoomBookingListSerializer(ModelSerializer):
    room_type_name = SerializerMethodField()
    customer_name = SerializerMethodField()
    number_of_guests = SerializerMethodField()
    check_in = SerializerMethodField()
    check_out = SerializerMethodField()

    class Meta:
        model = Room
        fields = '__all__'

    def get_room_type_name(self, obj):
        return obj.type.name if obj.type.name else None
    
    def get_today_booking(self, obj):
        # Get today's booking (if there is)
        return Booking.objects.filter(room=obj, check_in__lte=date.today(), check_out__gte=date.today()).order_by('check_in').first()

    def get_customer_name(self, obj):
        today_booking = self.get_today_booking(obj)
        return str(today_booking.transaction.customer) if today_booking else None
    
    def get_number_of_guests(self, obj):
        today_booking = self.get_today_booking(obj)
        return today_booking.number_of_guests if today_booking else None
    
    def get_check_in(self, obj):
        today_booking = self.get_today_booking(obj)
        return today_booking.check_in if today_booking else None

    def get_check_out(self, obj):
        today_booking = self.get_today_booking(obj)
        return today_booking.check_out if today_booking else None

