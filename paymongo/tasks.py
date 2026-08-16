from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
import logging
from .models import WebhookEvent
from bookings.models import Booking
from transactions.models import (
    AmenitiesAvailed, Billing, Payment, PaymentForChoices,
    PaymentMethod, PaymentStatus,
)
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
import json
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


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


def create_webhook_event(event_id, billing, event_type, payload):
    try:
        WebhookEvent.objects.create(
            event_id=event_id,
            billing=billing,
            event_type=event_type,
            payload=payload
        )
        logger.info('WebhookEvent saved: %s (type=%s)', event_id, event_type)
    except Exception as e:
        logging.error(f"Error creating Webhook event: {str(e)}")
        raise


def create_payment(billing, payment_type):
    """Create Payment records from DB records (rooms + boat). Returns created payments."""
    payment_method, _ = PaymentMethod.objects.get_or_create(mode=payment_type)
    paid_status, _ = PaymentStatus.objects.get_or_create(status='Paid')
    booking_ct = ContentType.objects.get_for_model(Booking)
    amenity_ct = ContentType.objects.get_for_model(AmenitiesAvailed)

    payments = []
    for booking in billing.bookings.all():
        payment = Payment.objects.create(
            customer_bill=billing,
            amount=booking.total_cost,
            date=timezone.now(),
            mop=payment_method,
            paymentFor=PaymentForChoices.ROOM,
            status=paid_status,
            content_type=booking_ct,
            object_id=booking.id,
        )
        payments.append(payment)
        logger.info('Payment saved: id=%s booking=%s amount=%s mop=%s',
                    payment.id, booking.id, payment.amount, payment_method)

    for availed in billing.amenities_availed.all():
        payment = Payment.objects.create(
            customer_bill=billing,
            amount=availed.total_cost,
            date=timezone.now(),
            mop=payment_method,
            paymentFor=PaymentForChoices.AMENITIES,
            status=paid_status,
            content_type=amenity_ct,
            object_id=availed.id,
        )
        payments.append(payment)
        logger.info('Payment saved: id=%s amenity_availed=%s amount=%s mop=%s',
                    payment.id, availed.id, payment.amount, payment_method)

    return payments


@shared_task
def process_event(payload):
    logger.info(payload)

    event_id = payload.get('data', {}).get('id')
    event_type = payload.get('data', {}).get('attributes', {}).get('type')

    # session object sits in data.attributes.data
    data = payload.get('data', {}).get('attributes', {}).get('data') or {}
    attrs = data.get('attributes') or {}
    payment_method_used = attrs.get('payment_method_used') or ''
    billing_id = int(attrs.get('description'))

    billing = Billing.objects.filter(id=billing_id).first()
    if not billing:
        logger.error('Webhook %s: billing %s not found', event_id, billing_id)
        return

    # PayMongo redelivers webhooks — event_id is unique, skip repeats
    if WebhookEvent.objects.filter(event_id=event_id).exists():
        logger.info('Webhook %s already processed, skipping', event_id)
        return

    create_webhook_event(event_id, billing, event_type, payload)

    payments = attrs.get('payments') or []
    paid = any(p.get('attributes', {}).get('status') == 'paid' for p in payments)
    if paid and event_type == 'checkout_session.payment.paid':
        created = create_payment(billing, payment_method_used)
        logger.info('Payment done for billing %s: %s payment record(s) created',
                    billing.id, len(created))
    else:
        logger.info('Webhook %s: no paid payment, skipping payment creation', event_id)
