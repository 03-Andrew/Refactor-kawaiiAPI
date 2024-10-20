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
    billing_id = serializers.IntegerField()
    return_url = serializers.URLField()

    # New fields for the payment record
    payment_for = serializers.CharField(required=False)  # Changed to CharField
    payment_status = serializers.CharField(required=False)  # Changed to CharField

    # Fields from Payment model
    content_type = serializers.CharField(required=False)  # ID for the content type
    object_id = serializers.IntegerField(required=False)  # Object ID for GenericForeignKey
    # Add any other fields you might want to pass

class GCashSourceSerializer(serializers.Serializer):
    amount = serializers.IntegerField()
    success_url = serializers.URLField()
    failed_url = serializers.URLField()
    billing_id = serializers.IntegerField()
    description = serializers.CharField(max_length=255)

    # New fields for the payment record
    payment_for = serializers.CharField(required=False)  # Changed to CharField
    payment_status = serializers.CharField(required=False)  # Changed to CharField

    # Fields from Payment model
    content_type = serializers.CharField(required=False)  # ID for the content type
    object_id = serializers.IntegerField(required=False)  # Object ID for GenericForeignKey
    # Add any other fields you might want to pass

class WebhookEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookEvent
        fields = '__all__'  # Include all fields from the WebhookEvent model

