from rest_framework import serializers
from .models import Transaction, Customer, Payment, GuestList, Amenities, AmenitiesAvailed, Activity, ActivitiesAvailed

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ['first_name', 'last_name']

class TransactionSerialzerBase(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = "__all__"

class TransactionSerializer(serializers.ModelSerializer):
    total_cost = serializers.SerializerMethodField()
    paid_amount = serializers.SerializerMethodField()
    running_balance = serializers.SerializerMethodField()
    customer = CustomerSerializer()
    
    class Meta:
        model = Transaction
        fields = "__all__"

    def get_total_cost(self, obj):
        return obj.total_cost or 0

    def get_paid_amount(self, obj):
        return obj.paid_amount or 0

    def get_running_balance(self, obj):
        return obj.running_balance or 0


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = "__all__"


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = "__all__"