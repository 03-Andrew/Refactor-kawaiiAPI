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
        return f"{obj.customer_bill.customer.first_name} {obj.customer_bill.customer.last_name}"
    
    class Meta:
        model = Booking
        fields = ['id', 'customer_bill', 'customer_name','room', 'room_type', 'check_in', 'check_out', 'adult_count', 'children_count', 'number_of_guests', 'status', 'created_at', 'number_of_nights', 'total_cost']

class RoomStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoomStatus
        fields = ['id', 'name']

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



class RoomTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoomType
        fields = ['id', 'name', 'price', 'description', 'good_for', 'max_children', 'max_adult']

class RoomTypeSerializer2(serializers.ModelSerializer):
    class Meta:
        model = RoomType
        fields = ['id', 'name']

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


