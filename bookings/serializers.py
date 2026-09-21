from datetime import date

from rest_framework import serializers

from .models import Booking, Room, RoomType, Inclusions
from transactions.models import AmenitiesAvailed

class BookingCustomerSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    contact_number = serializers.CharField(max_length=11)
    email = serializers.EmailField()

    class Meta:
        ref_name = "BookingCustomer"

class BookingRoomSerializer(serializers.Serializer):
    room_type = serializers.IntegerField(min_value=1)
    check_in = serializers.DateField(help_text="Check-in date (YYYY-MM-DD)")
    check_out = serializers.DateField(help_text="Check-out date (YYYY-MM-DD)")
    adult_count = serializers.IntegerField(min_value=1)
    children_count = serializers.IntegerField(default=0, min_value=0)
    extra_guest = serializers.IntegerField(default=0, min_value=0)
    room_number = serializers.IntegerField(required=False, default=None)

    class Meta:
        ref_name = "BookingRoom"

    def validate_room_type(self, value):
        if not RoomType.objects.filter(id=value).exists():
            raise serializers.ValidationError(f"Room type {value} does not exist.")
        return value

    def validate(self, data):
        today = date.today()
        if data['check_in'] < today:
            raise serializers.ValidationError({'check_in': 'Check-in date cannot be in the past.'})
        if data['check_out'] <= data['check_in']:
            raise serializers.ValidationError({'check_out': 'Check-out must be after check-in.'})
        return data

class OnlineBookingBoatSerializer(serializers.Serializer):
    head_count = serializers.IntegerField(min_value=1)
    time = serializers.TimeField(required=False, default="10:00")
    guests = serializers.ListField(
        child=serializers.CharField(), help_text="List of guest names for boat transfer"
    )

    class Meta:
        ref_name = "OnlineBookingBoat"

class OnlineBookingRequestSerializer(serializers.Serializer):
    customer = BookingCustomerSerializer()
    rooms = BookingRoomSerializer(many=True)
    boat = OnlineBookingBoatSerializer(required=False)
    class Meta:
        ref_name = "OnlineBookingRequest"

class OnsiteBookingRequestSerializer(serializers.Serializer):
    customer = BookingCustomerSerializer()
    booking = BookingRoomSerializer(many=True)

    class Meta:
        ref_name = "OnsiteBookingRequest"


class DayTourAmenitySerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1)
    head_count = serializers.IntegerField(min_value=1)

    class Meta:
        ref_name = "DayTourAmenity"


class DayTourActivitySerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1)
    hours = serializers.IntegerField(min_value=1)

    class Meta:
        ref_name = "DayTourActivity"


class DayTourRequestSerializer(serializers.Serializer):
    customer = BookingCustomerSerializer()
    guest_list = serializers.ListField(
        child=serializers.CharField(), required=False, default=list,
    )
    selected_amenities = DayTourAmenitySerializer(many=True, required=False, default=list)
    selected_activities = DayTourActivitySerializer(many=True, required=False, default=list)

    class Meta:
        ref_name = "DayTourRequest"


class BookingCountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = ['room', 'adult_count', 'children_count']

class BookingSerializer(serializers.ModelSerializer):
    """
    Single canonical serializer for Booking reads and writes.

    Computed fields delegate to model @property: number_of_nights,
    number_of_guests, total_cost, and customer_name (via Customer.full_name).

    Callers must use select_related('customer_bill__customer') to avoid N+1.
    """
    number_of_nights = serializers.ReadOnlyField()
    number_of_guests = serializers.ReadOnlyField()
    total_cost       = serializers.ReadOnlyField()
    customer_name    = serializers.CharField(
        source='customer_bill.customer.full_name', read_only=True,
    )

    class Meta:
        model = Booking
        fields = [
            'id', 'customer_bill', 'customer_name',
            'room', 'room_type',
            'check_in', 'check_out',
            'adult_count', 'children_count', 'extra_guest',
            'number_of_guests', 'status', 'created_at',
            'number_of_nights', 'total_cost',
        ]
        read_only_fields = ['created_at']

        def get_availed_boat_transfer(self, obj):
        # Get the AmenitiesAvailed object with 'boat transfer' amenity
            boat_transfer = AmenitiesAvailed.objects.filter(
                customer_bill=obj.customer_bill, amenity__amenity='boat transfer'
            ).first()
            
            # If the boat transfer exists, return the time; otherwise return None
            return boat_transfer.time if boat_transfer else "Not Availed"

class InclusionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Inclusions
        fields = ['inclusion']

class RoomTypeSerializer(serializers.ModelSerializer):
    # inclusions = InclusionSerializer(many=True, required=False)

    class Meta:
        model = RoomType
        fields = ['id', 'name', 'price', 'description', 'good_for', 'max_extra_guest']

class RoomTypeAvailabilitySerializer(serializers.ModelSerializer):
    total_rooms = serializers.IntegerField(read_only=True)
    booked_rooms = serializers.IntegerField(read_only=True)
    locked_rooms = serializers.IntegerField(read_only=True)
    available_rooms = serializers.IntegerField(read_only=True)
    maintenance_rooms = serializers.IntegerField(read_only=True)
    suggested_number_of_rooms_to_book = serializers.IntegerField(read_only=True)
    should_add_extra_guest = serializers.BooleanField(read_only=True)
    pair_with_other_rooms = serializers.BooleanField(read_only=True)
    can_accommodate_group = serializers.BooleanField(read_only=True)
    class Meta:
        model = RoomType
        fields = ['id', 'name', 'price', 'description', 'good_for', "total_rooms", "max_extra_guest",
                  "booked_rooms", "locked_rooms",  "available_rooms",  "maintenance_rooms",
                  'suggested_number_of_rooms_to_book','should_add_extra_guest', 'pair_with_other_rooms',
                  'can_accommodate_group']

class RoomSerializer(serializers.ModelSerializer):
    type = RoomTypeSerializer(read_only=True)
    type_id = serializers.PrimaryKeyRelatedField(
        queryset=RoomType.objects.all(), source='type', write_only=True
    )
    is_booked = serializers.BooleanField(default=False, read_only=True)
    class Meta:
        model = Room
        fields = ['id', 'number', 'type', 'type_id', 'status', 'is_booked']

class RoomTypeSelectionSerializerBase(serializers.Serializer):
    room_type_id = serializers.IntegerField()
    check_in = serializers.DateField(help_text="Check-in date (YYYY-MM-DD)")
    check_out = serializers.DateField(help_text="Check-out date (YYYY-MM-DD)")

class BulkLockRoomTypeSerializer(serializers.Serializer):
    turnstile_token = serializers.CharField(required=False, allow_blank=True ,default=None)
    holder_id =  serializers.CharField(required=False, allow_blank=True, default=None)
    rooms = RoomTypeSelectionSerializerBase(many=True)

class SingleLockRoomTypeSerializer(RoomTypeSelectionSerializerBase):
    turnstile_token = serializers.CharField(required=False, allow_blank=True ,default=None)
    holder_id =  serializers.CharField(required=False, allow_blank=True, default=None)
