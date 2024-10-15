from rest_framework import serializers
from .models import WebhookEvent
from transactions.models import Payment
from rest_framework.serializers import ModelSerializer


class CardPaymentSerializer(serializers.Serializer):
    amount = serializers.IntegerField()
    description = serializers.CharField(max_length=255)
    payment_method_allowed = serializers.ListField(
        child=serializers.ChoiceField(choices=["card", "gcash"])
    )
    payment_type = serializers.ChoiceField(choices=["card", "gcash"])
    card_number = serializers.CharField(max_length=16)
    exp_month = serializers.IntegerField()
    exp_year = serializers.IntegerField()
    cvc = serializers.CharField(max_length=4)
    billing_name = serializers.CharField(max_length=100)
    billing_email = serializers.EmailField()
    billing_phone = serializers.CharField(max_length=15)
    return_url = serializers.URLField()

class WebhookEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookEvent
        fields = ['event_type', 'payload', 'received_at']
