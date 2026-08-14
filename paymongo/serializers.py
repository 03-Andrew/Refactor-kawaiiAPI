from rest_framework import serializers
from .models import WebhookEvent

class LinkSerializer(serializers.Serializer):
    billing_id = serializers.CharField()
    payment_for = serializers.CharField()
    payment_status = serializers.CharField()
    content_type = serializers.CharField()
    object_id = serializers.CharField()
    amount = serializers.IntegerField()
    description = serializers.CharField(required=False, allow_blank=True)
    remarks = serializers.CharField(required=False, allow_blank=True)     

class WebhookEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookEvent
        fields = '__all__'  # Include all fields from the WebhookEvent model

class PaymongoPaymentSerializer(serializers.Serializer):
    amount = serializers.IntegerField()
    description = serializers.CharField(required=False, allow_blank=True)

