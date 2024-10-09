import hashlib
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
import hmac
import hashlib
from django.http import JsonResponse
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
    
#TEST WEBHOOK 1
class WebhookNotif(APIView):  
    def post(self, request, *args, **kwargs):
        try:
            # Load and print the JSON payload
            payload = json.loads(request.body)
            print("Received Webhook Notification:", json.dumps(payload, indent=4))  # Pretty print JSON

            event_type = payload['data']['attributes']['type']

            if event_type == 'source.chargeable':
                print("Source is chargeable!")
                # Handle source authorization (GCash or GrabPay)

            elif event_type == 'payment.paid':
                print("Payment was successful!")
                # Handle successful payment

            elif event_type == 'payment.failed':
                print("Payment failed.")
                # Handle failed payment

            elif event_type == 'link.payment.paid':
                print("Link payment was successful!")
                # Handle successful link payment

            elif event_type == 'payment.refunded':
                print("Payment was refunded successfully.")
                # Handle successful payment refund

            elif event_type == 'payment.refund.updated':
                print("Payment refund was updated.")
                # Handle refund update (successful or failed)

            elif event_type == 'checkout_session.payment.paid':
                print("Checkout session payment was successful!")
                # Handle successful Checkout Session payment

            else:
                print(f"Unhandled event type: {event_type}")
                # Log unhandled events or take necessary actions

            return Response({'status': 'success'}, status=status.HTTP_200_OK)

        except json.JSONDecodeError:
            # Handle case where the payload is not valid JSON
            return Response({'status': 'invalid payload'}, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, *args, **kwargs):
        # Optional: Handle GET requests if necessary
        return Response({'status': 'method not allowed'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)


#TEST WEBHOOK 2  
class WebhookNotif2(APIView):  
    def verify_signature(self, payload, received_signature, timestamp):
        """
        Verifies the Paymongo signature using HMAC and SHA256.
        """
        # Concatenate timestamp and the raw payload
        signature_base_string = f"{timestamp}.{payload}"
        
        # Create a HMAC SHA256 signature using your webhook secret key from settings
        computed_signature = hmac.new(
            bytes(settings.PAYMONGO_SECRET_KEY, 'utf-8'),
            bytes(signature_base_string, 'utf-8'),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(computed_signature, received_signature)

    def post(self, request, *args, **kwargs):
        # Capture Paymongo-Signature from headers
        received_signature_header = request.headers.get('Paymongo-Signature', '')
        if not received_signature_header:
            return JsonResponse({'status': 'missing signature'}, status=status.HTTP_400_BAD_REQUEST)

        # Extract signature values (timestamp, te or li signatures)
        try:
            parts = {k: v for k, v in (part.split('=') for part in received_signature_header.split(','))}
            timestamp = parts['t']
            received_signature = parts.get('te') or parts.get('li')  # Use 'te' for test mode, 'li' for live mode
        except ValueError:
            return JsonResponse({'status': 'invalid signature format'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Get the raw JSON payload (ensure you're getting the raw body)
        payload = request.body.decode('utf-8')

        # Verify the signature
        if not self.verify_signature(payload, received_signature, timestamp):
            return JsonResponse({'status': 'invalid signature'}, status=status.HTTP_400_BAD_REQUEST)

        # Print the received JSON payload in the terminal (for debugging purposes)
        print(json.dumps(json.loads(payload), indent=4))

        # Handle the event based on its type
        try:
            payload_data = json.loads(payload)
            event_type = payload_data['data']['attributes']['type']

            if event_type == 'source.chargeable':
                # Handle GCash or GrabPay source authorization
                print("Source is chargeable!")
                # Perform actions like creating a payment
            elif event_type == 'payment.paid':
                # Handle successful payment
                print("Payment was successful!")
                # Perform actions like updating your database
            elif event_type == 'payment.failed':
                # Handle failed payment
                print("Payment failed.")
                # Perform actions like notifying the user
            elif event_type == 'link.payment.paid':
                # Handle Link payment
                print("Link payment was successful!")
            elif event_type == 'payment.refunded':
                # Handle successful payment refund
                print("Payment has been refunded.")
            elif event_type == 'payment.refund.updated':
                # Handle updated payment refund (including failures)
                print("Payment refund status updated.")
            elif event_type == 'checkout_session.payment.paid':
                # Handle Checkout Session payment
                print("Checkout Session payment was successful!")

            return JsonResponse({'status': 'success'}, status=status.HTTP_200_OK)

        except json.JSONDecodeError:
            return JsonResponse({'status': 'invalid payload'}, status=status.HTTP_400_BAD_REQUEST)
    
    def get(self, request, *args, **kwargs):
        # Optional: Handle GET requests if necessary
        return JsonResponse({'status': 'method not allowed'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)
