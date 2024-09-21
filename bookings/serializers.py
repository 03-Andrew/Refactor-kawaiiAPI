from rest_framework import serializers
from .models import Booking, Room, RoomType, RoomStatus

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
        return f"{obj.transaction.customer.first_name} {obj.transaction.customer.last_name}"
    
    class Meta:
        model = Booking
        fields = ['transaction', 'customer_name','room', 'room_type', 'check_in', 'check_out', 'number_of_guests', 'status', 'created_at', 'number_of_nights', 'total_cost']

class RoomStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoomStatus
        fields = ['id', 'name']

class RoomTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoomType
        fields = ['id', 'name', 'price', 'description', 'good_for', 'max_children', 'max_adult']

class RoomSerializer(serializers.ModelSerializer):
    status = RoomStatusSerializer()
    type = RoomTypeSerializer()
    class Meta:
        model = Room
        fields = ['id', 'number', 'type', 'status']


class AvailableRoomSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    description = serializers.CharField()
    good_for = serializers.IntegerField()
    max_children = serializers.IntegerField()
    max_adult = serializers.IntegerField()
    count = serializers.IntegerField()
