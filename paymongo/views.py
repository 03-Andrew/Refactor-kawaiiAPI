import hashlib
from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
import base64
from rest_framework import generics
from .serializers import CardPaymentSerializer, WebhookEventSerializer
from transactions.models import Payment
import logging
import json
import requests
import hmac
import hashlib
from django.http import JsonResponse
from .models import WebhookEvent
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from rest_framework.permissions import IsAuthenticated
#from .serializers import PaymentSerializer, PaymentIntentListSerializer, CardPaymentSerializer
#from .serializers import PaymentIntentSerializer, CardPaymentMethodSerializer, AttachPaymentMethodSerializer

# class CsrfExemptSessionAuthentication(SessionAuthentication):
#     def enforce_csrf(self, request):
#         return  # To not perform the CSRF check

class CardPayment(APIView):
    # authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)
    # permission_classes = (IsAuthenticated,)  # Modify this as per your requirements

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
                "payment_intent_id": intent_response_data['data']['id'],  
                "payment_method_id": method_response_data['data']['id'], 
                "attached_method": attach_response_data['data']['id']
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

#GCASH
class GCashSource(APIView):
    # authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)
    # permission_classes = (IsAuthenticated,)  # Modify this as per your requirements

    def post(self, request, *args, **kwargs):
        data = request.data
        url = "https://api.paymongo.com/v1/sources"
        
        # Payload to create a GCash source
        payload = {
            "data": {
                "attributes": {
                    "amount": data.get('amount'),
                    "redirect": {
                        "success": data.get('success_url'),
                        "failed": data.get('failed_url'),
                    },
                    "billing": {
                        "name": data.get('name'),
                        "phone": data.get('phone'),
                        "email": data.get('email'),
                    },
                    "currency": "PHP",
                    "type": "gcash"
                }
            }
        }

        headers = {
            'accept': 'application/json',
            'authorization': f'Basic {base64.b64encode(f"{settings.PAYMONGO_SECRET_KEY}:".encode()).decode()}',
            'content-type': 'application/json',
        }

        # Send request to PayMongo to create a GCash source
        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            return Response(response.json(), status=status.HTTP_200_OK)
        else:
            return Response(response.json(), status=status.HTTP_400_BAD_REQUEST)


class GCashPayment(APIView):
    # authentication_classes = (CsrfExemptSessionAuthentication, BasicAuthentication)
    # permission_classes = (IsAuthenticated,)  # Modify this as per your requirements

    def post(self, request, *args, **kwargs):
        payload = request.data
        event_type = payload['data']['attributes']['type']


        # Check for chargeable event
        if event_type == 'source.chargeable':
            source_data = payload['data']['attributes']['data']
            source_id = source_data['id']
            amount = source_data['attributes']['amount']
            
            # Proceed to create a payment using the chargeable source
            self.create_payment(source_id, amount)

        return Response({"status": "success"}, status=status.HTTP_200_OK)
    
    def create_payment(self, source_id, amount):
        url = "https://api.paymongo.com/v1/payments"
        
        # Payload to create a payment
        payload = {
            "data": {
                "attributes": {
                    "amount": amount,
                    "source": {
                        "id": source_id,
                        "type": "source"
                    },
                    "currency": "PHP",
                    "description": "GCash Payment"
                }
            }
        }

        headers = {
            'accept': 'application/json',
            'authorization': f'Basic {base64.b64encode(f"{settings.PAYMONGO_SECRET_KEY}:".encode()).decode()}',
            'content-type': 'application/json',
        }

        # Send request to PayMongo to create a payment
        response = requests.post(url, json=payload, headers=headers)
        return response.json()

class WebhookNotif(APIView):
    def post(self, request, *args, **kwargs):
        try:
            # Get the signature from the headers
            paymongo_signature = request.headers.get('Paymongo-Signature', None)
            
            if not paymongo_signature:
                return Response({'status': 'error', 'message': 'Signature missing'}, status=status.HTTP_400_BAD_REQUEST)

            parts = paymongo_signature.split(',')
            timestamp = parts[0].split('=')[1]  
            test_signature = parts[1].split('=')[1]  

            raw_body = request.body
            signature_payload = f"{timestamp}.{raw_body.decode('utf-8')}"
            
            webhook_secret = settings.PAYMONGO_WEBHOOK_SECRET
            computed_signature = hmac.new(
                webhook_secret.encode('utf-8'),
                signature_payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()

            if computed_signature != test_signature:
                return Response({'status': 'error', 'message': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)

            # Proceed with processing the event if signature is validdd
            payload = request.data
            event_type = payload.get('data', {}).get('attributes', {}).get('type')

            if event_type:
                # Save the payload and event type to the database
                WebhookEvent.objects.create(
                    event_type=event_type,
                    payload=payload
                )
                return Response({'status': 'success'}, status=status.HTTP_200_OK)
            else:
                return Response({'status': 'event type missing'}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, *args, **kwargs):
        try:
            webhook_events = WebhookEvent.objects.all()
            serializer = WebhookEventSerializer(webhook_events, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        