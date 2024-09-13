from rest_framework import serializers
from .models import Transaction, Customer, Payment, GuestList, Amenities, AmenitiesAvailed, Activity, ActivitiesAvailed

class TransactionSerializer(serializers.ModelSerializer):
    total_cost = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = "__all__"

    def get_total_cost(self, obj):
        return obj.total_cost


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = "__all__"


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = "__all__"