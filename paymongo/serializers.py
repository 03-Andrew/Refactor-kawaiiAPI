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

# class CardPaymentSerializer(serializers.Serializer):
#     amount = serializers.IntegerField()
#     description = serializers.CharField(max_length=255)
#     card_number = serializers.CharField(max_length=16)
#     exp_month = serializers.IntegerField()
#     exp_year = serializers.IntegerField()
#     cvc = serializers.CharField(max_length=4)
#     billing_id = serializers.IntegerField()
#     return_url = serializers.URLField()
#     payment_for = serializers.CharField(required=False) 
#     payment_status = serializers.CharField(required=False)
#     content_type = serializers.CharField(required=False) 
#     object_id = serializers.IntegerField(required=False) 


# class GCashSourceSerializer(serializers.Serializer):
#     amount = serializers.IntegerField()
#     success_url = serializers.URLField()
#     failed_url = serializers.URLField()
#     billing_id = serializers.IntegerField()
#     description = serializers.CharField(max_length=255)
#     payment_for = serializers.CharField(required=False) 
#     payment_status = serializers.CharField(required=False)  
#     content_type = serializers.CharField(required=False)  
#     object_id = serializers.IntegerField(required=False) 
