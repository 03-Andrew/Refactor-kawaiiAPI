from rest_framework import serializers
from .models import Booking

class BookingSerializer(serializers.ModelSerializer):
    number_of_nights = serializers.SerializerMethodField()
    total_cost = serializers.SerializerMethodField()

    def get_number_of_nights(self, obj):
        return (obj.check_out - obj.check_in).days

    def get_total_cost(self, obj):
        # Implement your logic to calculate total cost based on room_type.price and number_of_nights
        return obj.room_type.price * self.get_number_of_nights(obj) if obj.room_type else 0

    class Meta:
        model = Booking
        fields = ['transaction', 'room', 'room_type', 'check_in', 'check_out', 'number_of_guests', 'status', 'created_at', 'number_of_nights', 'total_cost']


class AvailableRoomSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    description = serializers.CharField()
    good_for = serializers.IntegerField()
    max_children = serializers.IntegerField()
    max_adult = serializers.IntegerField()
    count = serializers.IntegerField()
