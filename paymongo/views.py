from django.conf import settings
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.core.mail import send_mail
try:
    from django_eventstream import send_event
except ImportError:
    def send_event(channel, event, data):
        pass

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

import logging
import requests
import hmac
import hashlib
import base64
import threading  

# Models
from transactions.models import Billing, Payment,PaymentMethod,PaymentStatus,PaymentFor
from transactions.models import Customer, Billing
from .models import WebhookEvent

# Serializers
from .serializers import WebhookEventSerializer, LinkSerializer


class CreateLink(APIView):
    def post(self, request, *args, **kwargs):
        # Serializer
        serializer = LinkSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        validated_data = serializer.validated_data
        description = []
        
        # Extract fields
        billing_id = validated_data.get('billing_id')
        payment_for = validated_data.get('payment_for')
        payment_status = validated_data.get('payment_status')
        content_type = validated_data.get('content_type')
        object_id = validated_data.get('object_id')
        custom_description = validated_data.get('description') 
        remarks = validated_data.get('remarks')

        # Append to description
        if billing_id:
            description.append(f"{billing_id}")
        if payment_for:
            description.append(f"{payment_for}")
        if payment_status:
            description.append(f"{payment_status}")
        if content_type:
            description.append(f"{content_type}")
        if object_id:
            description.append(f"{object_id}") 
        if custom_description: 
            description.append(custom_description)

        final_description = " - ".join(description)
        
        # Send request to PayMongo to create the link
        url = "https://api.paymongo.com/v1/links"
        payload = {
            "data": {
                "attributes": {
                    "amount": validated_data['amount'],
                    "description": final_description,  
                    "remarks": remarks  
                }
            }
        }

        headers = {
            'accept': 'application/json',
            'authorization': f'Basic {base64.b64encode(f"{settings.PAYMONGO_SECRET_KEY}:".encode()).decode()}',
            'content-type': 'application/json',
        }

        response = requests.post(url, json=payload, headers=headers)

        if response.status_code == 200:
            response_data = response.json().get('data', {}).get('attributes', {})
            return Response({ 
                'checkout_url': response_data.get('checkout_url'),  
                'amount': response_data.get('amount') / 100,  
            }, status=status.HTTP_200_OK)
        else:
            return Response(response.json(), status=status.HTTP_400_BAD_REQUEST)
       
class WebhookNotif(APIView):
    def post(self, request, *args, **kwargs):
        # Validate the signature
        if not self.validate_signature(request):
            return Response({'status': 'error', 'message': 'Invalid signature'}, status=status.HTTP_403_FORBIDDEN)

        response = Response({'status': 'success'}, status=status.HTTP_200_OK)
        
        threading.Thread(target=self.process_event, args=(request.data,)).start()
        logging.info("Started processing webhook event in a new thread.")

        return response

    def process_event(self, payload):
        try:
            print("HEYEYEHEYEHYEH")
            # Retrieve data 
            event_id = payload.get('data', {}).get('id')
            billing_description = payload.get('data', {}).get('attributes', {}).get('data', {}).get('attributes', {}).get('description', "")
            billing_split = billing_description.split(" - ")[0] if billing_description else None
            billing_id = Billing.objects.get(id=billing_split)
            event_type = payload.get('data', {}).get('attributes', {}).get('type')
            payment_status = payload.get('data', {}).get('attributes', {}).get('data', {}).get('attributes', {}).get('status')
            source_data = payload['data']['attributes']['data']
            source_id = source_data['id']
            amount = source_data['attributes']['amount']
            billing_info = source_data.get('attributes', {}).get('billing', None)
            description = source_data['attributes'].get('description', "")
            payment_type = source_data['attributes'].get('source', {}).get('type', "")
            
            # Save webhook
            self.create_webhook_event(event_id, billing_id, event_type, payload)
            
            # Create payment record and send email
            if payment_status == 'paid' and event_type == 'payment.paid':
                logging.info(f"Payment status is paid, proceeding with creating payment and sending email.")
                send_event('payments', 'payment_success', {
                    'message': 'Payment successful!',
                })
                
                self.create_payment(amount, billing_id, payment_type, description)
                self.send_email(billing_id.id, amount)
                
            
            send_event('payments', 'payment_success', {
                    'message': 'Payment successful!',
                })
            
            # if payment_status == 'chargeable':
            #     self.create_gcash_payment(source_id, amount, billing_info, description)

        except Exception as e:
            logging.error(f"Unexpected error processing event: {str(e)}")

    def validate_signature(self, request):
        paymongo_signature = request.headers.get('Paymongo-Signature', None)
        if not paymongo_signature:
            return False

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

        return computed_signature == test_signature

    def create_webhook_event(self, event_id, billing_id, event_type, payload):
        try:
            WebhookEvent.objects.create(
                event_id=event_id,
                billing=billing_id,
                event_type=event_type,
                payload=payload
            )
        except Exception as e:
            logging.error(f"Error creating Webhook event: {str(e)}")

    def create_payment(self, amount, billing_id, payment_type, description):
        description_parts = description.split(" - ")

        if len(description_parts) >= 5:
            payment_for_name = description_parts[1]
            payment_status_name = description_parts[2]
            content_type_name = description_parts[3]
            object_ids_str = description_parts[4].strip()
            
            object_ids = [int(id.strip()) for id in object_ids_str.split(",") if id.strip().isdigit()]
            num_of_objects = len(object_ids)
            amount_per_payment = amount / num_of_objects   # Calculate the amount for each payment

            try:
                payment_for = PaymentFor.objects.get(name=payment_for_name)
                payment_status = PaymentStatus.objects.get(status=payment_status_name)
                payment_method = PaymentMethod.objects.get(mode=payment_type)
                content_type = ContentType.objects.get(model=content_type_name)
            except (PaymentFor.DoesNotExist, PaymentStatus.DoesNotExist, PaymentMethod.DoesNotExist, ContentType.DoesNotExist) as e:
                logging.error(f"Error creating Payment record: {e}")
                return

            # Create payment records
            for object_id in object_ids:
                payment1 = Payment.objects.create(
                    customer_bill=billing_id,
                    amount=amount_per_payment / 100,  # convert cents to pesos
                    date=timezone.now(),
                    mop=payment_method,
                    paymentFor=payment_for,
                    status=payment_status,
                    content_type=content_type,
                    object_id=object_id,
                )
                logging.info(f"Payment successful. {billing_id}. Payment ID: {payment1.id}")
                print(f"Payment successful. {billing_id}. Payment ID: {payment1.id}")
                # payment_successful.send(sender=payment1.__class__, payment_id=payment1.id)

        else:
            logging.error("Description format is invalid.")

    def send_email(self, billing_id, amount):
        subject = f'Kawaii Resort: Billing Notification #{billing_id}'
        message = ''

        # fetch booking details
        try:
            response = requests.get(f'https://kawaii-app-nb6lb.ondigitalocean.app/api/billing-details/{billing_id}/')
            response.raise_for_status()
            booking_data = response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching booking details: {str(e)}")

        else:
            customer = booking_data.get("customer", {})
            bookings = booking_data.get("booking", [])
            amenities = booking_data.get("amenitiesAvailed", [])
            total_cost = booking_data.get("total_cost", 0.0)
            amount = amount/100

            # intro
            message = f"Dear {customer.get('first_name', 'Customer  ')},\n\n"
            message += f"Below are your booking details:\n\n"

            # Customer info
            message += f"Billing ID: {billing_id}\n"
            message += f"Customer Name: {customer.get('first_name', '')} {customer.get('last_name', '')}\n"
            message += f"Contact Number: {customer.get('contact_number', '')}\n"
            message += f"Email: {customer.get('email', '')}\n\n"

            # Booking info
            message += "Bookings:\n"
            for booking in bookings:
                message += (
                    f"- Booking ID: {booking.get('id')}\n"
                    f"  Check-in: {booking.get('check_in')}\n"
                    f"  Check-out: {booking.get('check_out')}\n"
                    f"  Guests: {booking.get('number_of_guests')}\n"
                    f"  Total Cost: PHP {booking.get('total_cost')}\n\n"
                )

            # Amenities info
            message += "Amenities Availed:\n"
            for amenity in amenities:
                amenity_details = amenity.get("amenity", {})
                rate_per_head = float(amenity_details.get("rate_per_head", 0))
                head_count = amenity.get("head_count", 0)
                total_amenity_cost = rate_per_head * head_count
                message += (
                    f"- Amenity: {amenity_details.get('amenity')}\n"
                    f"  Rate per Head: PHP {rate_per_head}\n"
                    f"  Head Count: {head_count}\n"
                    f"  Total Cost: PHP {total_amenity_cost}\n\n"
                )

            # outro
            message += f"Total Cost: PHP {total_cost}\n"
            message += f"Amount Paid (Down Payment): PHP {amount}\n\n"
            message += "Thank you for booking with us! Please await confirmation of your booking, and feel free to contact us if you have any questions.\n"

        # recipient email address
        recipient_list = [customer.get('email', '')]

         # Send the email
        try:
            send_mail(
                subject,
                message,
                settings.EMAIL_HOST_USER, 
                recipient_list,
                fail_silently=False,
            )
        except Exception as e:
            logging.error(f"Error sending email: {str(e)}")

    def get(self, request, *args, **kwargs):
        try:
            webhook_events = WebhookEvent.objects.all()
            serializer = WebhookEventSerializer(webhook_events, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            logging.error(f"Error retrieving webhook events: {str(e)}")
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

class ConfirmPayment(APIView):
    def get_customer_id(self, fName, lName, number):
        # Build the query dynamically based on the available parameters
        filters = {}
        if fName:
            filters['first_name__icontains'] = fName
        if lName:
            filters['last_name__icontains'] = lName
        if number:
            filters['contact_number'] = number

        # Filter the Customer model using the dynamic filters
        customer = Customer.objects.filter(**filters).order_by('-created_at').values().first()  # Order by created_at descending
        if customer:
            return customer["id"]
        else:
            return None


    def get(self, request):
        fName = request.query_params.get('fName', None)
        lName = request.query_params.get('lName', None)
        number = request.query_params.get('contact', None)
        customer=self.get_customer_id(fName, lName, number)
        if customer:
            bill = Billing.objects.filter(customer__exact=customer).values().first()
            print(bill)
            webhook = WebhookEvent.objects.filter(billing__exact=bill["id"]).values().first()
            if webhook and webhook["event_type"] in ["link.payment.paid", "payment.paid"]:
                return Response(True)
            else:
                return Response(False)
        else:
            return Response(False)

      

# class CardPayment(APIView):
#     def post(self, request):
#         # Step 1: Validate the incoming data using the combined serializer
#         combined_serializer = CardPaymentSerializer(data=request.data)

#         # Step 2: Check if the combined serializer is valid
#         if not combined_serializer.is_valid():
#             return Response({"error": combined_serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

#         # Extract validated data from the combined serializer
#         validated_data = combined_serializer.validated_data

#         # Extract billing_id from the request
#         billing_id = validated_data.get('billing_id')

#         try:
#             # Step 3: Retrieve the Billing instance and associated customer
#             billing = Billing.objects.get(id=billing_id)
#             customer = billing.customer

#             # Extract customer details
#             customer_name = str(customer)
#             customer_email = customer.email
#             customer_phone = customer.contact_number

#         except Billing.DoesNotExist:
#             return Response({"error": "Invalid billing ID"}, status=status.HTTP_400_BAD_REQUEST)

#         # New fields to include in the description
#         payment_for = validated_data.get('payment_for')
#         payment_status = validated_data.get('payment_status')
#         content_type = validated_data.get('content_type')
#         object_id = validated_data.get('object_id')

#         # Construct the description with all necessary fields
#         intent_data = {
#             "amount": validated_data['amount'],
#             "description": f"{billing_id} - {payment_for} - {payment_status} - {content_type} - {object_id} - {validated_data['description']}",
#             "billing_id": billing_id,
#         }

#         method_data = {
#             "card_number": validated_data['card_number'],
#             "exp_month": validated_data['exp_month'],
#             "exp_year": validated_data['exp_year'],
#             "cvc": validated_data['cvc'],
#             "billing_name": customer_name,
#             "billing_email": customer_email,
#             "billing_phone": customer_phone,
#             "billing_id": billing_id,
#         }

#         attach_data = {
#             "return_url": validated_data['return_url'],
#             "billing_id": billing_id,
#         }

#         try:
#             # Set up PayMongo API credentials
#             credentials = f"{settings.PAYMONGO_SECRET_KEY}:"
#             encoded_credentials = base64.b64encode(credentials.encode()).decode()

#             headers = {
#                 'Authorization': 'Basic ' + encoded_credentials,
#                 'Content-Type': 'application/json',
#             }

#             # Step 4: Create Payment Intent
#             payment_intent_response = self.create_payment_intent(intent_data, headers)
#             if payment_intent_response.status_code != 200:
#                 return Response(payment_intent_response.json(), status=payment_intent_response.status_code)

#             intent_response_data = payment_intent_response.json()
#             payment_intent_id = intent_response_data['data']['id']

#             # Step 5: Create Card Payment Method
#             payment_method_response = self.create_payment_method(method_data, headers)
#             if payment_method_response.status_code != 200:
#                 return Response(payment_method_response.json(), status=payment_method_response.status_code)

#             method_response_data = payment_method_response.json()
#             payment_method_id = method_response_data['data']['id']

#             # Step 6: Attach Payment Method to Payment Intent
#             attach_response = self.attach_payment_method(payment_intent_id, payment_method_id, attach_data, headers)
#             if attach_response.status_code != 200:
#                 return Response(attach_response.json(), status=attach_response.status_code)

#             attach_response_data = attach_response.json()

#             # Step 7: Return success response with the payment intent and method data
#             return Response({
#                 'status': 'success',
#                 "payment_intent_id": intent_response_data['data']['id'],
#                 "payment_method_id": method_response_data['data']['id'],
#                 "attached_method": attach_response_data['data']['id']
#             }, status=status.HTTP_200_OK)

#         except Exception as e:
#             return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

#     def create_payment_intent(self, intent_data, headers):
#         """Create a payment intent."""
#         payment_intent_url = 'https://api.paymongo.com/v1/payment_intents'
#         intent_payload = {
#             "data": {
#                 "attributes": {
#                     "amount": intent_data['amount'],
#                     "currency": "PHP",
#                     "description": intent_data['description'],
#                     "payment_method_allowed": ["card"],
#                 },
#             }
#         }
#         return requests.post(payment_intent_url, json=intent_payload, headers=headers)

#     def create_payment_method(self, method_data, headers):
#         """Create a payment method."""
#         payment_method_url = 'https://api.paymongo.com/v1/payment_methods'
#         method_payload = {
#             "data": {
#                 "attributes": {
#                     "type": "card",
#                     "details": {
#                         "card_number": method_data['card_number'],
#                         "exp_month": method_data['exp_month'],
#                         "exp_year": method_data['exp_year'],
#                         "cvc": method_data['cvc'],
#                     },
#                     "billing": {
#                         "name": method_data['billing_name'],
#                         "email": method_data['billing_email'],
#                         "phone": method_data['billing_phone'],
#                     },
#                 },
#             }
#         }
#         return requests.post(payment_method_url, json=method_payload, headers=headers)

#     def attach_payment_method(self, payment_intent_id, payment_method_id, attach_data, headers):
#         """Attach the payment method to the payment intent."""
#         attach_url = f'https://api.paymongo.com/v1/payment_intents/{payment_intent_id}/attach'
#         attach_payload = {
#             "data": {
#                 "attributes": {
#                     "payment_method": payment_method_id,
#                     "return_url": attach_data['return_url'],
#                 },
#             }
#         }
#         return requests.post(attach_url, json=attach_payload, headers=headers)

# class GCashSource(APIView):
#     def post(self, request, *args, **kwargs):
#         # Step 1: Validate the incoming data using the serializer
#         serializer = GCashSourceSerializer(data=request.data)

#         # Step 2: Check if the serializer is valid
#         if not serializer.is_valid():
#             return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

#         # Extract validated data from the serializer
#         validated_data = serializer.validated_data

#         # Step 3: Extract billing_id and retrieve customer information
#         billing_id = validated_data.get('billing_id')

#         try:
#             billing = Billing.objects.get(id=billing_id)
#             customer = billing.customer

#             # Extract customer details
#             customer_name = str(customer)
#             customer_email = customer.email
#             customer_phone = customer.contact_number

#         except Billing.DoesNotExist:
#             return Response({"error": "Invalid billing ID"}, status=status.HTTP_400_BAD_REQUEST)

#         payment_for = validated_data.get('payment_for')
#         payment_status = validated_data.get('payment_status')  
#         content_type = validated_data.get('content_type') 
#         object_id = validated_data.get('object_id')  

#         # Step 4: Prepare the payload for creating a GCash source
#         url = "https://api.paymongo.com/v1/sources"
#         custom_description = validated_data.get('description') 
#         description = f"{billing_id} - {payment_for} - {payment_status} - {content_type} - {object_id} - {custom_description}"

#         payload = {
#             "data": {
#                 "attributes": {
#                     "amount": validated_data['amount'],
#                     "redirect": {
#                         "success": validated_data['success_url'],
#                         "failed": validated_data['failed_url'],
#                     },
#                     "billing": {
#                         "name": customer_name,
#                         "phone": customer_phone,
#                         "email": customer_email,
#                     },
#                     "currency": "PHP",
#                     "type": "gcash",
#                     "description": description 
#                 }
#             }
#         }

#         headers = {
#             'accept': 'application/json',
#             'authorization': f'Basic {base64.b64encode(f"{settings.PAYMONGO_SECRET_KEY}:".encode()).decode()}',
#             'content-type': 'application/json',
#         }

#         # Step 5: Send request to PayMongo to create a GCash source
#         response = requests.post(url, json=payload, headers=headers)

#         if response.status_code == 200:
#             checkout_url = response.json().get('data', {}).get('attributes', {}).get('redirect', {}).get('checkout_url')
#             src_id =  response.json().get('data', {}).get('id')
#             return Response({'status': 'success', 'src_id': src_id,'checkout_url': checkout_url}, status=status.HTTP_200_OK)
#         else:
#             return Response(response.json(), status=status.HTTP_400_BAD_REQUEST)


    # def create_gcash_payment(self, source_id, amount, billing_info, description):
    #     url = "https://api.paymongo.com/v1/payments"

    #     payload = {
    #         "data": {
    #             "attributes": {
    #                 "amount": amount,
    #                 "source": {
    #                     "id": source_id,
    #                     "type": "source"
    #                 },
    #                 "currency": "PHP",
    #                 "description": description,
    #                 "billing": {
    #                     "name": billing_info['name'],
    #                     "email": billing_info['email'],
    #                     "phone": billing_info['phone']
    #                 }
    #             }
    #         }
    #     }

    #     headers = {
    #         'accept': 'application/json',
    #         'authorization': f'Basic {base64.b64encode(f"{settings.PAYMONGO_SECRET_KEY}:".encode()).decode()}',
    #         'content-type': 'application/json',
    #     }
        
    #     response = requests.post(url, json=payload, headers=headers)
    #     return response.json()