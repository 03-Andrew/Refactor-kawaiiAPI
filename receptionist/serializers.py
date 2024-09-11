from rest_framework.serializers import ModelSerializer, StringRelatedField, SerializerMethodField
from bookings.models import Booking

class PendingBookingsSerializer(ModelSerializer):
    class Meta:
        model = Booking
        fields = '__all__'
