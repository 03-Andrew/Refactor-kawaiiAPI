from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
import logging
from .models import WebhookEvent
from transactions.models import Billing, Payment,PaymentMethod,PaymentStatus
from transactions.models import Customer, Billing
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django_eventstream import send_event


@shared_task
def send_email(subject, message, recipient_list):
    try:
        return send_mail(
            subject,
            message,
            settings.EMAIL_HOST_USER, 
            recipient_list,
            fail_silently=False,
        )
    except Exception as e:
        logging.error(f"Error sending email: {str(e)}")

@shared_task
def create_webhook_event(event_id, billing_id, event_type, payload):
    try:
        WebhookEvent.objects.create(
            event_id=event_id,
            billing=billing_id,
            event_type=event_type,
            payload=payload
        )
    except Exception as e:
        logging.error(f"Error creating Webhook event: {str(e)}")


@shared_task
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
            payment_status = PaymentStatus.objects.get(status=payment_status_name)
            payment_method = PaymentMethod.objects.get(mode=payment_type)
            content_type = ContentType.objects.get(model=content_type_name)
        except (PaymentStatus.DoesNotExist, PaymentMethod.DoesNotExist, ContentType.DoesNotExist) as e:
            logging.error(f"Error creating Payment record: {e}")
            return
        # Create payment records
        for object_id in object_ids:
            payment1 = Payment.objects.create(
                customer_bill=billing_id,
                amount=amount_per_payment / 100,  # convert cents to pesos
                date=timezone.now(),
                mop=payment_method,
                paymentFor=payment_for_name,
                status=payment_status,
                content_type=content_type,
                object_id=object_id,
            )
            logging.info(f"Payment successful. {billing_id}. Payment ID: {payment1.id}")
            print(f"Payment successful. {billing_id}. Payment ID: {payment1.id}")
            # payment_successful.send(sender=payment1.__class__, payment_id=payment1.id)
    else:
        logging.error("Description format is invalid.")


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


