from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
import logging
from .models import WebhookEvent
from bookings.models import Booking
from transactions.models import (
    AmenitiesAvailed, Billing, Payment, PaymentForChoices,
    PaymentMethod, PaymentStatus, BillingStatus
)
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
import json
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


def send_email(subject, message, recipient_list, html_message=None):
    try:
        return send_mail(
            subject,
            message,
            settings.EMAIL_HOST_USER,
            recipient_list,
            fail_silently=False,
            html_message=html_message,
        )
    except Exception as e:
        logger.error(f"Error sending email: {str(e)}")


def format_booking_confirmation_email(billing, amount_paid=None):
    customer = billing.customer
    first_name = customer.first_name if customer else "Guest"
    subject = f"Booking Confirmation #{billing.id}"

    # Plain text fallback
    lines = [
        f"Dear {first_name},",
        "",
        "Thank you for your payment! Your booking has been confirmed.",
        "",
        "--- BOOKING SUMMARY ---",
        f"Billing Reference: #{billing.id}",
        f"Guest Name: {customer.full_name if customer else ''}",
        f"Contact Number: {customer.contact_number if customer else ''}",
        f"Email: {customer.email if customer else ''}",
        "",
    ]

    bookings = billing.bookings.select_related('room_type').all()
    if bookings.exists():
        lines.append("Rooms:")
        for b in bookings:
            room_name = b.room_type.name if b.room_type else "Room"
            lines.append(f"  - {room_name} ({b.check_in} to {b.check_out})")
            lines.append(f"    Guests: {b.number_of_guests} (Adults: {b.adult_count}, Children: {b.children_count}, Extra: {b.extra_guest or 0})")
            lines.append(f"    Subtotal: PHP {b.total_cost:,.2f}")
        lines.append("")

    amenities = billing.amenities_availed.select_related('amenity').all()
    if amenities.exists():
        lines.append("Boat Transfers / Amenities:")
        for a in amenities:
            amenity_name = a.amenity.amenity if a.amenity else "Amenity"
            rate = a.amenity.rate_per_head if a.amenity else 0
            lines.append(f"  - {amenity_name} ({a.head_count} guest{'s' if a.head_count != 1 else ''} @ PHP {rate:,.2f})")
            lines.append(f"    Subtotal: PHP {a.total_cost:,.2f}")
        lines.append("")

    lines.append(f"Total Amount: PHP {billing.total_cost:,.2f}")
    if amount_paid is not None:
        lines.append(f"Amount Paid: PHP {amount_paid:,.2f}")

    lines.extend([
        "",
        "We look forward to welcoming you to the resort!",
        "If you have any questions, please reply to this email or contact us.",
    ])
    text_content = "\n".join(lines)

    # HTML version rendered from template
    html_content = None
    try:
        context = {
            'billing': billing,
            'customer': customer,
            'bookings': bookings,
            'amenities': amenities,
            'amount_paid': amount_paid,
        }
        html_content = render_to_string('emails/booking_confirmation.html', context)
    except Exception as e:
        logger.error(f"Error rendering booking confirmation HTML template: {str(e)}")

    return subject, text_content, html_content


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
        logger.error(f"Error creating Webhook event: {str(e)}")
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


def update_billing_paid(billing_id):
    billing = Billing.objects.get(id=billing_id)
    billing.status = BillingStatus.BOOKING_PAID
    billing.save()
    logger.info('Billing %s status updated to %s', billing_id, BillingStatus.BOOKING_PAID)
    return billing


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

        # 1. Update billing status to Booking Paid
        billing = update_billing_paid(billing.id)

        # 2. Send booking confirmation email to customer (HTML + Plaintext fallback)
        if billing.customer and billing.customer.email:
            total_paid = sum(p.amount for p in created)
            subject, text_message, html_message = format_booking_confirmation_email(billing, amount_paid=total_paid)
            send_email(subject, text_message, [billing.customer.email], html_message=html_message)
            logger.info('Confirmation email sent to %s for billing %s',
                        billing.customer.email, billing.id)
    else:
        logger.info('Webhook %s: no paid payment, skipping payment creation', event_id)

