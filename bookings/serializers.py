from datetime import date

from rest_framework import serializers

from .models import Booking, Room, RoomType, BookingStatus


# ── Online Booking Request Schemas ──────────────────────────────

class OnlineBookingCustomerSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=100, help_text="Customer's first name")
    last_name = serializers.CharField(max_length=100, help_text="Customer's last name")
    contact_number = serializers.CharField(max_length=11, help_text="11-digit contact number")
    email = serializers.EmailField(help_text="Customer's email address")

    class Meta:
        ref_name = "OnlineBookingCustomer"


class OnlineBookingRoomSerializer(serializers.Serializer):
    room_type = serializers.IntegerField(help_text="Room type ID")
    check_in = serializers.DateField(help_text="Check-in date (YYYY-MM-DD)")
    check_out = serializers.DateField(help_text="Check-out date (YYYY-MM-DD)")
    adult_count = serializers.IntegerField(min_value=1, help_text="Number of adults")
    children_count = serializers.IntegerField(default=0, min_value=0, help_text="Number of children")
    extra_guest = serializers.IntegerField(default=0, min_value=0, help_text="Extra guests beyond room capacity")
    price = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Total price for this room booking")
    number_of_guests = serializers.IntegerField(min_value=1, help_text="Total guest count")

    class Meta:
        ref_name = "OnlineBookingRoom"

    def validate_room_type(self, value):
        if not RoomType.objects.filter(id=value).exists():
            raise serializers.ValidationError(f"Room type {value} does not exist.")
        return value

    def validate(self, data):
        today = date.today()
        check_in = data['check_in']
        check_out = data['check_out']

        if check_in < today:
            raise serializers.ValidationError({'check_in': 'Check-in date cannot be in the past.'})
        if check_out <= check_in:
            raise serializers.ValidationError({'check_out': 'Check-out must be after check-in.'})
        return data


class OnlineBookingBoatSerializer(serializers.Serializer):
    head_count = serializers.IntegerField(min_value=1, help_text="Number of guests boarding the boat")
    time = serializers.TimeField(required=False, default="10:00", help_text="Boat departure time (HH:MM)")
    guests = serializers.ListField(
        child=serializers.CharField(), help_text="List of guest names for boat transfer"
    )

    class Meta:
        ref_name = "OnlineBookingBoat"


class OnlineBookingPaymentSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Down payment amount")

    class Meta:
        ref_name = "OnlineBookingPayment"


class OnlineBookingRequestSerializer(serializers.Serializer):
    customer = OnlineBookingCustomerSerializer(help_text="Customer information")
    rooms = OnlineBookingRoomSerializer(many=True, help_text="Room bookings (one or more)")
    boat = OnlineBookingBoatSerializer(many=True, required=False, help_text="Optional boat transfers")
    payment = OnlineBookingPaymentSerializer(help_text="Payment details")

    class Meta:
        ref_name = "OnlineBookingRequest"
        
        
class BookingsAllSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = '__all__'

class BookingCountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = ['room', 'adult_count', 'children_count']

class BookingSerializer(serializers.ModelSerializer):
    number_of_nights = serializers.SerializerMethodField()
    total_cost = serializers.SerializerMethodField()
    customer_name = serializers.SerializerMethodField()

    def get_number_of_nights(self, obj):
        return (obj.check_out - obj.check_in).days

    def get_total_cost(self, obj):
        # Implement your logic to calculate total cost based on room_type.price and number_of_nights
        return obj.room_type.price * self.get_number_of_nights(obj) if obj.room_type else 0
    
    def get_customer_name(self, obj):
        # Fetch the customer's full name via the related transaction
        return f"{obj.customer_bill.customer.first_name} {obj.customer_bill.customer.last_name}"
    
    class Meta:
        model = Booking
        fields = ['id', 'customer_bill', 'customer_name','room', 'room_type', 'check_in', 'check_out', 'adult_count', 'children_count', 'extra_guest','number_of_guests', 'status', 'created_at', 'number_of_nights', 'total_cost']


class BookingSerializer2(serializers.ModelSerializer):
    room_type = serializers.CharField(source='room_type.name', read_only=True)
    room_type_id = serializers.IntegerField(source='room_type.id', read_only=True)
    number_of_nights = serializers.SerializerMethodField()
    total_cost = serializers.SerializerMethodField()
    status = serializers.CharField(source='status.name', read_only=True)

    def get_number_of_nights(self, obj):
        return (obj.check_out - obj.check_in).days

    def get_total_cost(self, obj):
        # Implement your logic to calculate total cost based on room_type.price and number_of_nights
        return obj.room_type.price * self.get_number_of_nights(obj) if obj.room_type else 0
    
    class Meta:
        model = Booking
        fields = ['id','room', 'room_type', 'room_type_id', 'check_in', 'check_out','adult_count','children_count', 'number_of_guests', 'status', 'created_at', 'number_of_nights', 'total_cost']


class BookingSerializer3(serializers.ModelSerializer):
    number_of_nights = serializers.SerializerMethodField()
    total_cost = serializers.SerializerMethodField()

    def get_number_of_nights(self, obj):
        return (obj.check_out - obj.check_in).days

    def get_total_cost(self, obj):
        # Implement your logic to calculate total cost based on room_type.price and number_of_nights
        return (obj.room_type.price + (obj.extra_guest*1500)) * self.get_number_of_nights(obj) if obj.room_type else 0
    
    class Meta:
        model = Booking
        fields = ['id', 'customer_bill', 'room_type', 'check_in', 'check_out', 'adult_count', 'children_count', 'extra_guest','number_of_nights', 'total_cost']




class RoomTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoomType
        fields = ['id', 'name', 'price', 'description', 'good_for', 'max_children', 'max_adult']


class RoomAllSerializer(serializers.ModelSerializer):
    type = RoomTypeSerializer()
    class Meta:
        model = Room
        fields = '__all__'


class RoomSerializer(serializers.ModelSerializer):
    type = RoomTypeSerializer(read_only=True)
    type_id = serializers.PrimaryKeyRelatedField(
        queryset=RoomType.objects.all(), source='type', write_only=True
    )
    is_booked = serializers.BooleanField(default=False, read_only=True)
    class Meta:
        model = Room
        fields = ['id', 'number', 'type', 'type_id', 'status', 'is_booked']


class RoomSerializer2(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = '__all__'


class AvailableRoomSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    description = serializers.CharField()
    good_for = serializers.IntegerField()
    max_children = serializers.IntegerField()
    max_adult = serializers.IntegerField()
    count = serializers.IntegerField()


class AvailableRoomSerializer2(serializers.ModelSerializer):
    status = serializers.CharField(source='status.name', read_only=True)
    type = serializers.CharField(source='type.name', read_only=True)
    type_id = serializers.IntegerField(source='type.id', read_only=True)
    max_children = serializers.IntegerField(source='type.max_children', read_only=True)
    max_adult = serializers.IntegerField(source='type.max_children', read_only=True)
    price = serializers.FloatField(source='type.price', read_only=True)
    class Meta:
        model = Room
        fields = ['id', 'number', 'type', 'type_id','max_children', 'max_adult','status', 'price']
        
        
class CurrentRoomBookings(serializers.ModelSerializer):
    room_type = serializers.CharField(source='room_type.name', read_only=True)

    class Meta:
        model = Booking
        fields = '__all__'


