from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
import base64
from rest_framework import generics
from .serializers import CardPaymentSerializer
from transactions.models import Payment
import logging
import json
import requests
#from .serializers import PaymentSerializer, PaymentIntentListSerializer, CardPaymentSerializer
#from .models import PaymentMethod, PaymentIntent, AttachedPaymentMethod
#from .serializers import PaymentIntentSerializer, CardPaymentMethodSerializer, AttachPaymentMethodSerializer

class CardPayment(APIView):

    def post(self, request):
        # Step 1: Validate the incoming data using the combined serializer
        combined_serializer = CardPaymentSerializer(data=request.data)

        # Step 2: Check if the combined serializer is valid
        if not combined_serializer.is_valid():
            return Response({"error": combined_serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        # Extract validated data from the combined serializer
        validated_data = combined_serializer.validated_data

        # Separate validated data for clarity
        intent_data = {
            "amount": validated_data['amount'],
            "description": validated_data['description'],
            "payment_method_allowed": validated_data['payment_method_allowed'],
        }
        
        method_data = {
            "payment_type": validated_data['payment_type'],
            "card_number": validated_data['card_number'],
            "exp_month": validated_data['exp_month'],
            "exp_year": validated_data['exp_year'],
            "cvc": validated_data['cvc'],
            "billing_name": validated_data['billing_name'],
            "billing_email": validated_data['billing_email'],
            "billing_phone": validated_data['billing_phone'],
        }

        attach_data = {
            "return_url": validated_data['return_url']
        }

        try:
            # Set up PayMongo API credentials
            credentials = f"{settings.PAYMONGO_SECRET_KEY}:"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()

            headers = {
                'Authorization': 'Basic ' + encoded_credentials,
                'Content-Type': 'application/json',
            }

            # Step 3: Create Payment Intent
            payment_intent_response = self.create_payment_intent(intent_data, headers)
            if payment_intent_response.status_code != 200:
                return Response(payment_intent_response.json(), status=payment_intent_response.status_code)

            intent_response_data = payment_intent_response.json()
            payment_intent_id = intent_response_data['data']['id']

            # Step 4: Create Card Payment Method
            payment_method_response = self.create_payment_method(method_data, headers)
            if payment_method_response.status_code != 200:
                return Response(payment_method_response.json(), status=payment_method_response.status_code)

            method_response_data = payment_method_response.json()
            payment_method_id = method_response_data['data']['id']

            # Step 5: Attach Payment Method to Payment Intent
            attach_response = self.attach_payment_method(payment_intent_id, payment_method_id, attach_data, headers)
            if attach_response.status_code != 200:
                return Response(attach_response.json(), status=attach_response.status_code)

            attach_response_data = attach_response.json()

            # Step 6: Return success response with the payment intent and method data
            return Response({
                "payment_intent": intent_response_data,
                "payment_method": method_response_data,
                "attached_method": attach_response_data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def create_payment_intent(self, intent_data, headers):
        """Create a payment intent."""
        payment_intent_url = 'https://api.paymongo.com/v1/payment_intents'
        intent_payload = {
            "data": {
                "attributes": {
                    "amount": intent_data['amount'],
                    "currency": "PHP",
                    "description": intent_data['description'],
                    "payment_method_allowed": intent_data['payment_method_allowed'],
                }
            }
        }
        return requests.post(payment_intent_url, json=intent_payload, headers=headers)

    def create_payment_method(self, method_data, headers):
        """Create a payment method."""
        payment_method_url = 'https://api.paymongo.com/v1/payment_methods'
        method_payload = {
            "data": {
                "attributes": {
                    "type": method_data['payment_type'],
                    "details": {
                        "card_number": method_data['card_number'],
                        "exp_month": method_data['exp_month'],
                        "exp_year": method_data['exp_year'],
                        "cvc": method_data['cvc'],
                    },
                    "billing": {
                        "name": method_data['billing_name'],
                        "email": method_data['billing_email'],
                        "phone": method_data['billing_phone'],
                    }
                }
            }
        }
        return requests.post(payment_method_url, json=method_payload, headers=headers)

    def attach_payment_method(self, payment_intent_id, payment_method_id, attach_data, headers):
        """Attach the payment method to the payment intent."""
        attach_url = f'https://api.paymongo.com/v1/payment_intents/{payment_intent_id}/attach'
        attach_payload = {
            "data": {
                "attributes": {
                    "payment_method": payment_method_id,
                    "return_url": attach_data['return_url']
                }
            }
        }
        return requests.post(attach_url, json=attach_payload, headers=headers)
