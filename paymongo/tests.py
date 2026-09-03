from unittest.mock import patch
from django.test import TestCase
from bookings.models import Booking, RoomType, BookingStatus
from transactions.models import Customer, Billing, BillingStatus, Payment, Amenities, AmenitiesAvailed
from paymongo.models import WebhookEvent
from paymongo.tasks import process_event


class PaymongoWebhookTasksTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            first_name="Juan",
            last_name="Dela Cruz",
            contact_number="09123456789",
            email="juan@example.com",
        )
        self.billing = Billing.objects.create(
            customer=self.customer,
            status=BillingStatus.PENDING,
        )
        self.room_type = RoomType.objects.create(
            name="Deluxe Villa",
            price=3000.00,
            max_extra_guest=1,
            good_for=2,
        )
        self.booking = Booking.objects.create(
            customer_bill=self.billing,
            room_type=self.room_type,
            check_in="2027-05-01",
            check_out="2027-05-03",
            adult_count=2,
            children_count=0,
            extra_guest=0,
            status=BookingStatus.PENDING,
        )
        self.amenity = Amenities.objects.create(
            amenity="Boat Transfer",
            rate_per_head=250.00,
        )
        self.amenity_availed = AmenitiesAvailed.objects.create(
            customer_bill=self.billing,
            amenity=self.amenity,
            head_count=2,
        )

    def _sample_webhook_payload(self, event_id="evt_test_123", status="paid"):
        return {
            "data": {
                "id": event_id,
                "attributes": {
                    "type": "checkout_session.payment.paid",
                    "data": {
                        "attributes": {
                            "description": str(self.billing.id),
                            "payment_method_used": "gcash",
                            "payments": [
                                {
                                    "attributes": {
                                        "status": status,
                                        "amount": int(self.billing.total_cost * 100),
                                    }
                                }
                            ],
                        }
                    },
                },
            }
        }

    @patch('paymongo.tasks.send_mail')
    def test_process_event_paid_updates_billing_and_sends_email(self, mock_send_mail):
        payload = self._sample_webhook_payload()

        process_event(payload)

        # 1. Billing status updated to Booking Paid
        self.billing.refresh_from_db()
        self.assertEqual(self.billing.status, BillingStatus.BOOKING_PAID)

        # 2. Payments created for room + boat
        payments = Payment.objects.filter(customer_bill=self.billing)
        self.assertEqual(payments.count(), 2)

        # 3. Webhook event recorded
        self.assertTrue(WebhookEvent.objects.filter(event_id="evt_test_123").exists())

        # 4. Confirmation email sent to customer (both text and HTML)
        mock_send_mail.assert_called_once()
        subject, message, sender, recipient_list = mock_send_mail.call_args[0]
        html_message = mock_send_mail.call_args[1].get('html_message')
        self.assertIn(f"#{self.billing.id}", subject)
        self.assertIn("Juan", message)
        self.assertIn("Deluxe Villa", message)
        self.assertIn("Boat Transfer", message)
        self.assertEqual(recipient_list, ["juan@example.com"])
        self.assertIsNotNone(html_message)
        self.assertIn("THE RESORT", html_message)
        self.assertIn(f"#{self.billing.id}", html_message)

    @patch('paymongo.tasks.send_mail')
    def test_duplicate_webhook_ignored(self, mock_send_mail):
        payload = self._sample_webhook_payload(event_id="evt_dup_999")

        # First run
        process_event(payload)
        self.assertEqual(Payment.objects.filter(customer_bill=self.billing).count(), 2)
        self.assertEqual(mock_send_mail.call_count, 1)

        # Second run with same event_id
        process_event(payload)
        # Should not create duplicate payments or send another email
        self.assertEqual(Payment.objects.filter(customer_bill=self.billing).count(), 2)
        self.assertEqual(mock_send_mail.call_count, 1)
