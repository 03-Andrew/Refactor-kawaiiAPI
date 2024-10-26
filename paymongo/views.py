import hashlib
from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
import base64
from rest_framework import generics
from .serializers import CardPaymentSerializer, GCashSourceSerializer, WebhookEventSerializer, LinkSerializer
from transactions.models import Billing, Payment,PaymentMethod,PaymentStatus,PaymentFor
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
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import threading                    

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
            "billing_id": billing_id,
        }

        method_data = {
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
                'status': 'success',
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
                    "payment_method_allowed": ["card"],
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
                    "type": "card",
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

        payment_for = validated_data.get('payment_for')
        payment_status = validated_data.get('payment_status')  
        content_type = validated_data.get('content_type') 
        object_id = validated_data.get('object_id')  

        # Step 4: Prepare the payload for creating a GCash source
        url = "https://api.paymongo.com/v1/sources"
        custom_description = validated_data.get('description') 
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
                    "description": description 
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
            checkout_url = response.json().get('data', {}).get('attributes', {}).get('redirect', {}).get('checkout_url')
            src_id =  response.json().get('data', {}).get('id')
            return Response({'status': 'success', 'src_id': src_id,'checkout_url': checkout_url}, status=status.HTTP_200_OK)
        else:
            return Response(response.json(), status=status.HTTP_400_BAD_REQUEST)

class CreateLink(APIView):
    def post(self, request, *args, **kwargs):
        serializer = LinkSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        validated_data = serializer.validated_data

        remarks = []
        billing_id = validated_data.get('billing_id')
        payment_for = validated_data.get('payment_for')
        payment_status = validated_data.get('payment_status')
        content_type = validated_data.get('content_type')
        object_id = validated_data.get('object_id')

        if billing_id:
            remarks.append(f"{billing_id}")
        if payment_for:
            remarks.append(f"{payment_for}")
        if payment_status:
            remarks.append(f"{payment_status}")
        if content_type:
            remarks.append(f"{content_type}")
        if object_id:
            remarks.append(f"{object_id}")

        remarks = " - ".join(remarks) if remarks else ""
        url = "https://api.paymongo.com/v1/links"

        payload = {
            "data": {
                "attributes": {
                    "amount": validated_data['amount'],
                    "description": validated_data['description'],
                    "remarks": remarks  
                }
            }
        }

        headers = {
            'accept': 'application/json',
            'authorization': f'Basic {base64.b64encode(f"{settings.PAYMONGO_SECRET_KEY}:".encode()).decode()}',
            'content-type': 'application/json',
        }

        # Send request to PayMongo to create the link
        response = requests.post(url, json=payload, headers=headers)

        if response.status_code == 200:
            response_data = response.json().get('data', {}).get('attributes', {})
            return Response({
                'id': response.json().get('data', {}).get('id'),  
                'checkout_url': response_data.get('checkout_url'),  # URL for payment
                'amount': response_data.get('amount') / 100,  
                'description': response_data.get('description'),  
                'status': response_data.get('status'), 
                'remarks': response_data.get('remarks'),  
                'reference_number': response_data.get('reference_number')  # Unique reference number
            }, status=status.HTTP_200_OK)
        else:
            return Response(response.json(), status=status.HTTP_400_BAD_REQUEST)
        
class WebhookNotif(APIView):
    def post(self, request, *args, **kwargs):
        # Validate the signature
        if not self.validate_signature(request):
            return Response({'status': 'error', 'message': 'Invalid signature'}, status=status.HTTP_403_FORBIDDEN)
        
        threading.Thread(target=self.process_event, args=(request.data,)).start()
        return Response({'status': 'success'}, status=status.HTTP_200_OK)

    def process_event(self, payload):
        """Processes the payment event from Paymongo."""
        try:
            # Retrieve necessary data from the payload
            event_id = payload.get('data', {}).get('id')
            event_type = payload.get('data', {}).get('type')
            source_data = payload['data']['attributes']['data']
            payment_status = source_data['attributes']['status']
            amount = source_data['attributes']['amount']
            payment_type = source_data['attributes']['source']['type']
            remarks = source_data['attributes'].get('remarks', "")

            if event_type == 'link.payment.paid' and payment_status == 'paid':
                billing_id = self.create_payment(amount, payment_type, remarks)
                self.create_webhook_event(event_id, billing_id, event_type, payload)

        except Exception as e:
            logging.error(f"Unexpected error processing event: {str(e)}")

    def validate_signature(self, request):
        """Validates the Paymongo signature."""
        paymongo_signature = request.headers.get('Paymongo-Signature', None)
        if not paymongo_signature:
            return False

        parts = paymongo_signature.split(',')
        timestamp = parts[0].split('=')[1]
        test_signature = parts[1].split('=')[1]
        raw_body = request.body
        signature_payload = f"{timestamp}.{raw_body.decode('utf-8')}"
        webhook_secret = settings.PAYMONGO_WEBHOOK_SECRET

        # Generate the computed signature
        computed_signature = hmac.new(
            webhook_secret.encode('utf-8'),
            signature_payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return computed_signature == test_signature

    def create_webhook_event(self, event_id, billing_id, event_type, payload):
        """Creates a webhook event record."""
        try:
            WebhookEvent.objects.create(
                event_id=event_id,
                billing=billing_id,
                event_type=event_type,
                payload=payload
            )
        except Exception as e:
            logging.error(f"Error creating Webhook event: {str(e)}")

    def create_payment(self, amount, payment_type, billing_data):
        """Creates a payment record."""
        billing_data_parts = billing_data.split(" - ")

        if len(billing_data_parts) >= 5:
            billing_id = billing_data_parts[0]
            payment_for_name = billing_data_parts[1]
            payment_status_name = billing_data_parts[2]
            content_type_name = billing_data_parts[3]
            object_id = billing_data_parts[4]

            try:
                payment_for = PaymentFor.objects.get(name=payment_for_name)
                payment_status = PaymentStatus.objects.get(status=payment_status_name)
                payment_method = PaymentMethod.objects.get(mode=payment_type)
                content_type = ContentType.objects.get(model=content_type_name)

                # Create a Payment model
                logging.info(f"Creating Payment record for billing_id: {billing_id}")
                Payment.objects.create(
                    customer_bill=billing_id,
                    amount=amount / 100,  # convert from cents
                    date=timezone.now(),
                    mop=payment_method,
                    paymentFor=payment_for,
                    status=payment_status,
                    content_type=content_type,
                    object_id=object_id,
                )
                return billing_id  # Return billing_id for logging

            except (PaymentFor.DoesNotExist, PaymentStatus.DoesNotExist, PaymentMethod.DoesNotExist, ContentType.DoesNotExist) as e:
                logging.error(f"Error creating Payment record: {e}")
                return None

        logging.error("Billing data format is invalid.")
        return None

    def get(self, request, *args, **kwargs):
        try:
            webhook_events = WebhookEvent.objects.all()
            serializer = WebhookEventSerializer(webhook_events, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            logging.error(f"Error retrieving webhook events: {str(e)}")
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)