import hashlib
from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
import base64
from rest_framework import generics
from .serializers import CardPaymentSerializer, GCashSourceSerializer, WebhookEventSerializer
from transactions.models import Billing
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
import threading
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from rest_framework.permissions import IsAuthenticated
#from .serializers import PaymentSerializer, PaymentIntentListSerializer, CardPaymentSerializer
#from .serializers import PaymentIntentSerializer, CardPaymentMethodSerializer, AttachPaymentMethodSerializer

# class CsrfExemptSessionAuthentication(SessionAuthentication):
#     def enforce_csrf(self, request):
#         return  # To not perform the CSRF check

class CardPayment(APIView):
    def post(self, request):
        # Step 1: Validate the incoming data using the combined serializer
        combined_serializer = CardPaymentSerializer(data=request.data)

        # Step 2: Check if the combined serializer is valid
        if not combined_serializer.is_valid():
            return Response({"error": combined_serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        # Extract validated data from the combined serializer
        validated_data = combined_serializer.validated_data

        # Extract billing_id from the request
        billing_id = validated_data.get('billing_id')

        try:
            # Step 3: Retrieve the Billing instance and associated customer
            billing = Billing.objects.get(id=billing_id)
            customer = billing.customer

            # Extract customer details
            customer_name = str(customer)
            customer_email = customer.email
            customer_phone = customer.contact_number

        except Billing.DoesNotExist:
            return Response({"error": "Invalid billing ID"}, status=status.HTTP_400_BAD_REQUEST)

        # New fields to include in the description
        payment_for = validated_data.get('payment_for')
        payment_status = validated_data.get('payment_status')
        content_type = validated_data.get('content_type')
        object_id = validated_data.get('object_id')

        # Construct the description with all necessary fields
        intent_data = {
            "amount": validated_data['amount'],
            "description": f"{billing_id} - {payment_for} - {payment_status} - {content_type} - {object_id} - {validated_data['description']}",
            "payment_method_allowed": validated_data['payment_method_allowed'],
            "billing_id": billing_id,
        }

        method_data = {
            "payment_type": validated_data['payment_type'],
            "card_number": validated_data['card_number'],
            "exp_month": validated_data['exp_month'],
            "exp_year": validated_data['exp_year'],
            "cvc": validated_data['cvc'],
            "billing_name": customer_name,
            "billing_email": customer_email,
            "billing_phone": customer_phone,
            "billing_id": billing_id,
        }

        attach_data = {
            "return_url": validated_data['return_url'],
            "billing_id": billing_id,
        }

        try:
            # Set up PayMongo API credentials
            credentials = f"{settings.PAYMONGO_SECRET_KEY}:"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()

            headers = {
                'Authorization': 'Basic ' + encoded_credentials,
                'Content-Type': 'application/json',
            }

            # Step 4: Create Payment Intent
            payment_intent_response = self.create_payment_intent(intent_data, headers)
            if payment_intent_response.status_code != 200:
                return Response(payment_intent_response.json(), status=payment_intent_response.status_code)

            intent_response_data = payment_intent_response.json()
            payment_intent_id = intent_response_data['data']['id']

            # Step 5: Create Card Payment Method
            payment_method_response = self.create_payment_method(method_data, headers)
            if payment_method_response.status_code != 200:
                return Response(payment_method_response.json(), status=payment_method_response.status_code)

            method_response_data = payment_method_response.json()
            payment_method_id = method_response_data['data']['id']

            # Step 6: Attach Payment Method to Payment Intent
            attach_response = self.attach_payment_method(payment_intent_id, payment_method_id, attach_data, headers)
            if attach_response.status_code != 200:
                return Response(attach_response.json(), status=attach_response.status_code)

            attach_response_data = attach_response.json()

            # Step 7: Return success response with the payment intent and method data
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
                },
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
                    },
                },
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
                    "return_url": attach_data['return_url'],
                },
            }
        }
        return requests.post(attach_url, json=attach_payload, headers=headers)

#GCASH
class GCashSource(APIView):
    def post(self, request, *args, **kwargs):
        # Step 1: Validate the incoming data using the serializer
        serializer = GCashSourceSerializer(data=request.data)

        # Step 2: Check if the serializer is valid
        if not serializer.is_valid():
            return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        # Extract validated data from the serializer
        validated_data = serializer.validated_data

        # Step 3: Extract billing_id and retrieve customer information
        billing_id = validated_data.get('billing_id')

        try:
            billing = Billing.objects.get(id=billing_id)
            customer = billing.customer

            # Extract customer details
            customer_name = str(customer)
            customer_email = customer.email
            customer_phone = customer.contact_number

        except Billing.DoesNotExist:
            return Response({"error": "Invalid billing ID"}, status=status.HTTP_400_BAD_REQUEST)

        # New fields to include in the description
        payment_for = validated_data.get('payment_for')
        payment_status = validated_data.get('payment_status')  # Default to 'pending' if not provided
        content_type = validated_data.get('content_type')  # Get content type from validated data
        object_id = validated_data.get('object_id')  # Using object_id from input or default to billing_id

        # Step 4: Prepare the payload for creating a GCash source
        url = "https://api.paymongo.com/v1/sources"
        custom_description = validated_data.get('description')  # Get the custom description
        description = f"{billing_id} - {payment_for} - {payment_status} - {content_type} - {object_id} - {custom_description}"

        payload = {
            "data": {
                "attributes": {
                    "amount": validated_data['amount'],
                    "redirect": {
                        "success": validated_data['success_url'],
                        "failed": validated_data['failed_url'],
                    },
                    "billing": {
                        "name": customer_name,
                        "phone": customer_phone,
                        "email": customer_email,
                    },
                    "currency": "PHP",
                    "type": "gcash",
                    "description": description  # Use the formatted description
                }
            }
        }

        headers = {
            'accept': 'application/json',
            'authorization': f'Basic {base64.b64encode(f"{settings.PAYMONGO_SECRET_KEY}:".encode()).decode()}',
            'content-type': 'application/json',
        }

        # Step 5: Send request to PayMongo to create a GCash source
        response = requests.post(url, json=payload, headers=headers)

        if response.status_code == 200:
            return Response(response.json(), status=status.HTTP_200_OK)
        else:
            return Response(response.json(), status=status.HTTP_400_BAD_REQUEST)
        
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
                return Response({'status': 'error', 'message': 'Invalid signature'}, status=status.HTTP_403_FORBIDDEN)

            # Respond immediately after validating the payload
            response = Response({'status': 'success'}, status=status.HTTP_200_OK)

            # Extract payload data
            payload = request.data
            event_id = payload.get('data', {}).get('id')
            billing_description = payload.get('data', {}).get('attributes', {}).get('data', {}).get('attributes', {}).get('description', "")
            billing_split = billing_description.split(" - ")[0] if billing_description else None
            billing_id = Billing.objects.get(id=billing_split)
            event_type = payload.get('data', {}).get('attributes', {}).get('type')
            status = payload.get('data', {}).get('attributes', {}).get('data', {}).get('attributes', {}).get('status')

            # Process webhook event in a separate thread
            threading.Thread(
                target=self.process_webhook_event,
                args=(event_id, billing_id, event_type, status, payload)
            ).start()

            # Return success response immediately
            return response

        except Exception as e:
            logging.error(f"Error processing webhook: {str(e)}")
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def process_webhook_event(self, event_id, billing_id, event_type, status, payload):
        """
        Processes the webhook event by saving it to the database and handling chargeable events.
        """
        try:
            # Save the WebhookEvent record to the database
            WebhookEvent.objects.create(
                event_id=event_id,
                billing=billing_id,
                event_type=event_type,
                payload=payload
            )

            # Handle the chargeable event in a separate method
            if status == 'chargeable':
                threading.Thread(
                    target=self.handle_chargeable_event,
                    args=(payload,)
                ).start()

        except Exception as e:
            logging.error(f"Error saving webhook event: {str(e)}")

    def handle_chargeable_event(self, payload):
        try:
            source_data = payload['data']['attributes']['data']
            source_id = source_data['id']
            amount = source_data['attributes']['amount']
            billing_info = source_data['attributes']['billing']
            description = source_data['attributes'].get('description', "GCash Payment")

            # Call the method to create the GCash payment
            self.create_gcash_payment(source_id, amount, billing_info, description)

        except Exception as e:
            logging.error(f"Error handling chargeable event: {str(e)}")

    def create_gcash_payment(self, source_id, amount, billing_info, description):
        url = "https://api.paymongo.com/v1/payments"
        payload = {
            "data": {
                "attributes": {
                    "amount": amount,
                    "source": {
                        "id": source_id,
                        "type": "source"
                    },
                    "currency": "PHP",
                    "description": description,
                    "billing": {
                        "name": billing_info['name'],
                        "email": billing_info['email'],
                        "phone": billing_info['phone']
                    }
                }
            }
        }

        headers = {
            'accept': 'application/json',
            'authorization': f'Basic {base64.b64encode(f"{settings.PAYMONGO_SECRET_KEY}:".encode()).decode()}',
            'content-type': 'application/json',
        }

        try:
            response = requests.post(url, json=payload, headers=headers)
            return response.json()
        except Exception as e:
            logging.error(f"Error creating GCash payment: {str(e)}")
            return None

    def get(self, request, *args, **kwargs):
        try:
            webhook_events = WebhookEvent.objects.all()
            serializer = WebhookEventSerializer(webhook_events, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            logging.error(f"Error retrieving webhook events: {str(e)}")
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# class GCashPayment(APIView):
#     def post(self, request, *args, **kwargs):
#         payload = request.data
#         event_type = payload['data']['attributes']['type']


#         # Check for chargeable event
#         if event_type == 'source.chargeable':
#             source_data = payload['data']['attributes']['data']
#             source_id = source_data['id']
#             amount = source_data['attributes']['amount']
            
#             # Proceed to create a payment using the chargeable source
#             self.create_payment(source_id, amount)

#         return Response({"status": "success"}, status=status.HTTP_200_OK)
    
#     def create_payment(self, source_id, amount):
#         url = "https://api.paymongo.com/v1/payments"
        
#         # Payload to create a payment
#         payload = {
#             "data": {
#                 "attributes": {
#                     "amount": amount,
#                     "source": {
#                         "id": source_id,
#                         "type": "source"
#                     },
#                     "currency": "PHP",
#                     "description": "GCash Payment"
#                 }
#             }
#         }

#         headers = {
#             'accept': 'application/json',
#             'authorization': f'Basic {base64.b64encode(f"{settings.PAYMONGO_SECRET_KEY}:".encode()).decode()}',
#             'content-type': 'application/json',
#         }

#         # Send request to PayMongo to create a payment
#         response = requests.post(url, json=payload, headers=headers)
#         return response.json()

# class WebhookNotif(APIView):
#     def post(self, request, *args, **kwargs):
#         try:
#             # Get the signature from the headers
#             paymongo_signature = request.headers.get('Paymongo-Signature', None)
            
#             if not paymongo_signature:
#                 return Response({'status': 'error', 'message': 'Signature missing'}, status=status.HTTP_400_BAD_REQUEST)

#             parts = paymongo_signature.split(',')
#             timestamp = parts[0].split('=')[1]  
#             test_signature = parts[1].split('=')[1]  

#             raw_body = request.body
#             signature_payload = f"{timestamp}.{raw_body.decode('utf-8')}"
            
#             webhook_secret = settings.PAYMONGO_WEBHOOK_SECRET
#             computed_signature = hmac.new(
#                 webhook_secret.encode('utf-8'),
#                 signature_payload.encode('utf-8'),
#                 hashlib.sha256
#             ).hexdigest()

#             if computed_signature != test_signature:
#                 return Response({'status': 'error', 'message': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)

#             # Proceed with processing the event if signature is validdd
#             payload = request.data
#             event_type = payload.get('data', {}).get('attributes', {}).get('type')

#             if event_type:
#                 # Save the payload and event type to the database
#                 WebhookEvent.objects.create(
#                     event_type=event_type,
#                     payload=payload
#                 )
#                 return Response({'status': 'success'}, status=status.HTTP_200_OK)
#             else:
#                 return Response({'status': 'event type missing'}, status=status.HTTP_400_BAD_REQUEST)

#         except Exception as e:
#             return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)

#     def get(self, request, *args, **kwargs):
#         try:
#             webhook_events = WebhookEvent.objects.all()
#             serializer = WebhookEventSerializer(webhook_events, many=True)
#             return Response(serializer.data, status=status.HTTP_200_OK)

#         except Exception as e:
#             return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        