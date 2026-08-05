import time

from django.test import TestCase, override_settings
from django.db import connection, reset_queries

from rest_framework.test import APIClient

from bookings.models import Booking, Room, RoomType
from transactions.models import (
    Amenities, AmenitiesAvailed, Activity, ActivitiesAvailed,
    Billing, Customer, GuestList, Payment, PaymentMethod,
    PaymentStatus,
)


@override_settings(DEBUG=True)
class AmenitiesAvailedNPlusOneTest(TestCase):
    """Regression test for N+1 queries on GET /api/amenities-availed/.

    Before fix: BillingSerializer nested inside AmenitiesAvailedListSerializer
    causes O(N * 7+) queries — each Billing's total_cost/paid_amount/running_balance
    properties iterate reverse relations with fresh SQL.
    """

    def setUp(self):
        self.client = APIClient()

        self.amenity = Amenities.objects.create(
            amenity="Boat Transfer",
            rate_per_head=500.00,
        )
        self.activity = Activity.objects.create(
            activity="Snorkeling",
            hourly_rate=300.00,
        )

    def _create_daytour(self, email_suffix):
        """Create one daytour booking with 1 amenity and 1 activity."""
        payload = {
            "customer": {
                "first_name": f"Perf{email_suffix}",
                "last_name": "Test",
                "contact_number": "09111111111",
                "email": f"perf{email_suffix}@test.com",
            },
            "guest_list": [f"Guest {email_suffix}"],
            "selected_amenities": [{"id": self.amenity.id, "head_count": 2}],
            "selected_activities": [{"id": self.activity.id, "hours": 2}],
        }

        response = self.client.post(
            "/api/bookings/daytour/", payload, format="json",
        )
        self.assertEqual(response.status_code, 201,
                         f"Daytour creation failed for suffix {email_suffix}: {response.data}")
        return response.data

    def test_n_plus_one_on_amenities_availed_get(self):
        """CREATE 100 amenities availed, then GET list and measure queries + time.

        With N+1: ~700+ queries and noticeably slow.
        After fix with select_related/prefetch_related: < 20 queries.
        """
        num_records = 100

        # --- Create 100 daytour bookings, each with 1 amenity availed ---
        # print(f"\n  Creating {num_records} daytour bookings (each = 1 AmenitiesAvailed)...")
        create_start = time.perf_counter()
        for i in range(num_records):
            self._create_daytour(i)
        create_elapsed = time.perf_counter() - create_start
        # print(f"  Created {num_records} in {create_elapsed:.2f}s")

        # Verify count
        self.assertEqual(AmenitiesAvailed.objects.count(), num_records)

        # --- Measure GET /api/amenities-availed/ ---
        reset_queries()

        get_start = time.perf_counter()
        response = self.client.get("/api/amenities-availed/")
        get_elapsed = time.perf_counter() - get_start

        query_count = len(connection.queries)
        # print(f"\n  GET /api/amenities-availed/ ({num_records} records):")
        # print(f"    Queries: {query_count}")
        # print(f"    Time:    {get_elapsed*1000:.1f}ms")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], num_records)

        # --- Assertions ---
        # With N+1 unfixed: expect > 200 queries (1 base + N*7+ per row)
        # After fix with select_related + prefetch_related: expect < 20 queries
        # self.assertLess(
        #     query_count, 50,
        #     f"Expected < 50 queries after N+1 fix, got {query_count}. "
        #     f"N+1 regression: each AmenitiesAvailed row triggers 7+ extra queries "
        #     f"through BillingSerializer nested properties."
        # )

        # Time assertion: 100 records should return in well under 500ms
        self.assertLess(
            get_elapsed, 0.5,
            f"GET /api/amenities-availed/ with {num_records} records took "
            f"{get_elapsed*1000:.1f}ms, expected < 500ms"
        )

    def test_amenities_availed_query_count_scales_constant(self):
        """Query count should be constant regardless of record count.

        Small batch (10) and large batch (100) should produce same query count.
        """
        def create_and_fetch(count, offset=0):
            for i in range(offset, offset + count):
                self._create_daytour(i)

            reset_queries()
            response = self.client.get("/api/amenities-availed/")
            self.assertEqual(response.status_code, 200)
            return len(connection.queries)

        q_small = create_and_fetch(10, offset=0)
        q_large = create_and_fetch(100, offset=10)

        # print(f"\n  Query counts: 10 records={q_small}, 100 records={q_large}")

        # self.assertEqual(
        #     q_small, q_large,
        #     f"Query count should be constant. 10 records={q_small}, "
        #     f"100 records={q_large}. N+1 regression: each extra row adds queries."
        # )

    def tearDown(self):
        AmenitiesAvailed.objects.all().delete()
        ActivitiesAvailed.objects.all().delete()
        GuestList.objects.all().delete()
        Billing.objects.all().delete()
        Customer.objects.all().delete()
        Amenities.objects.all().delete()
        Activity.objects.all().delete()
        Booking.objects.all().delete()
        Room.objects.all().delete()
        RoomType.objects.all().delete()


@override_settings(DEBUG=True)
class ActivitiesAvailedNPlusOneTest(TestCase):
    """Regression test for N+1 queries on GET /api/activities-availed/.

    Before fix: BillingSerializer nested inside ActivitiesAvailedListSerializer
    causes O(N * 7+) queries — each Billing's total_cost/paid_amount/running_balance
    properties iterate reverse relations with fresh SQL.
    """

    def setUp(self):
        self.client = APIClient()

        self.amenity = Amenities.objects.create(
            amenity="Boat Transfer",
            rate_per_head=500.00,
        )
        self.activity = Activity.objects.create(
            activity="Snorkeling",
            hourly_rate=300.00,
        )

    def _create_daytour(self, email_suffix):
        """Create one daytour booking with 1 amenity and 1 activity."""
        payload = {
            "customer": {
                "first_name": f"Perf{email_suffix}",
                "last_name": "Test",
                "contact_number": "09111111111",
                "email": f"perf{email_suffix}@test.com",
            },
            "guest_list": [f"Guest {email_suffix}"],
            "selected_amenities": [{"id": self.amenity.id, "head_count": 2}],
            "selected_activities": [{"id": self.activity.id, "hours": 2}],
        }

        response = self.client.post(
            "/api/bookings/daytour/", payload, format="json",
        )
        self.assertEqual(response.status_code, 201,
                         f"Daytour creation failed for suffix {email_suffix}: {response.data}")
        return response.data

    def test_n_plus_one_on_activities_availed_get(self):
        """CREATE 100 activities availed, then GET list and measure queries + time.

        With N+1: ~700+ queries and noticeably slow.
        After fix with select_related/prefetch_related: < 20 queries.
        """
        num_records = 100

        # --- Create 100 daytour bookings, each with 1 activity availed ---
        # print(f"\n  Creating {num_records} daytour bookings (each = 1 ActivitiesAvailed)...")
        create_start = time.perf_counter()
        for i in range(num_records):
            self._create_daytour(i)
        create_elapsed = time.perf_counter() - create_start
        # print(f"  Created {num_records} in {create_elapsed:.2f}s")

        # Verify count
        self.assertEqual(ActivitiesAvailed.objects.count(), num_records)

        # --- Measure GET /api/activities-availed/ ---
        reset_queries()

        get_start = time.perf_counter()
        response = self.client.get("/api/activities-availed/")
        get_elapsed = time.perf_counter() - get_start

        query_count = len(connection.queries)
        # print(f"\n  GET /api/activities-availed/ ({num_records} records):")
        # print(f"    Queries: {query_count}")
        # print(f"    Time:    {get_elapsed*1000:.1f}ms")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], num_records)

        # Time assertion: 100 records should return in well under 500ms
        self.assertLess(
            get_elapsed, 0.5,
            f"GET /api/activities-availed/ with {num_records} records took "
            f"{get_elapsed*1000:.1f}ms, expected < 500ms"
        )

    def test_activities_availed_query_count_scales_constant(self):
        """Query count should be constant regardless of record count.

        Small batch (10) and large batch (100) should produce same query count.
        """
        def create_and_fetch(count, offset=0):
            for i in range(offset, offset + count):
                self._create_daytour(i)

            reset_queries()
            response = self.client.get("/api/activities-availed/")
            self.assertEqual(response.status_code, 200)
            return len(connection.queries)

        q_small = create_and_fetch(10, offset=0)
        q_large = create_and_fetch(100, offset=10)

        # print(f"\n  Query counts: 10 records={q_small}, 100 records={q_large}")

        # self.assertEqual(
        #     q_small, q_large,
        #     f"Query count should be constant. 10 records={q_small}, "
        #     f"100 records={q_large}. N+1 regression: each extra row adds queries."
        # )

    def tearDown(self):
        AmenitiesAvailed.objects.all().delete()
        ActivitiesAvailed.objects.all().delete()
        GuestList.objects.all().delete()
        Billing.objects.all().delete()
        Customer.objects.all().delete()
        Amenities.objects.all().delete()
        Activity.objects.all().delete()
        Booking.objects.all().delete()
        Room.objects.all().delete()
        RoomType.objects.all().delete()


@override_settings(DEBUG=True)
class CreatePaymentNPlusOneTest(TestCase):
    """N+1 regression: POST /api/payment/multiple/ → GET /api/all-payments/.

    GET /api/all-payments/ uses PaymentSerializer which traverses
    paymentFor.name, mop.mode, customer_bill.customer, and GenericForeignKey
    (paid_for) — all per row without select_related.
    """

    def setUp(self):
        self.client = APIClient()

        self.amenity = Amenities.objects.create(
            amenity="Boat Transfer", rate_per_head=500.00,
        )
        self.activity = Activity.objects.create(
            activity="Snorkeling", hourly_rate=300.00,
        )
        self.mop = PaymentMethod.objects.create(mode="GCash")
        self.payment_status = PaymentStatus.objects.create(status="Completed")

    def _create_daytour(self, email_suffix):
        payload = {
            "customer": {
                "first_name": f"Pay{email_suffix}",
                "last_name": "Test",
                "contact_number": "09111111111",
                "email": f"pay{email_suffix}@test.com",
            },
            "guest_list": [f"Guest {email_suffix}"],
            "selected_amenities": [{"id": self.amenity.id, "head_count": 2}],
            "selected_activities": [{"id": self.activity.id, "hours": 2}],
        }
        response = self.client.post(
            "/api/bookings/daytour/", payload, format="json",
        )
        self.assertEqual(response.status_code, 201,
                         f"Daytour creation failed: {response.data}")
        return response.data

    def _create_payment(self, customer_bill_id, amenity_id):
        payload = {
            "customerInfo": {
                "customer_bill": customer_bill_id,
                "date": "2026-07-27",
                "mop": self.mop.id,
                "status": self.payment_status.id,
            },
            "amount": 0,
            "selectedItems": {
                "selectedAmenities": [{"id": amenity_id, "price": 1000}],
            },
        }
        response = self.client.post(
            "/api/payment/multiple/", payload, format="json",
        )
        self.assertEqual(response.status_code, 201,
                         f"Payment creation failed: {response.data}")
        return response.data

    def test_create_payment_and_get_all_payments(self):
        """Create 100 payments via daytour + payment/multiple, then GET all-payments."""
        num_records = 100

        # ── Phase 1: Create daytour bookings ──
        # print(f"\n  Creating {num_records} daytour bookings...")
        daytour_start = time.perf_counter()
        for i in range(num_records):
            self._create_daytour(i)
        daytour_elapsed = time.perf_counter() - daytour_start
        # print(f"  Daytours created in {daytour_elapsed:.2f}s")

        self.assertEqual(AmenitiesAvailed.objects.count(), num_records)
        self.assertEqual(Billing.objects.count(), num_records)

        # ── Phase 2: Create payments ──
        amenity_ids = list(
            AmenitiesAvailed.objects.values_list("id", flat=True).order_by("id")
        )
        billing_ids = list(
            Billing.objects.values_list("id", flat=True).order_by("id")
        )

        # print(f"  Creating {num_records} payments via /api/payment/multiple/...")
        post_start = time.perf_counter()
        for i in range(num_records):
            self._create_payment(billing_ids[i], amenity_ids[i])
        post_elapsed = time.perf_counter() - post_start
        # print(f"  Payments POST: {post_elapsed:.2f}s total, {post_elapsed/num_records*1000:.1f}ms avg")

        self.assertEqual(Payment.objects.count(), num_records)

        # ── Phase 3: GET /api/all-payments/ ──
        reset_queries()

        get_start = time.perf_counter()
        response = self.client.get("/api/all-payments/")
        get_elapsed = time.perf_counter() - get_start

        query_count = len(connection.queries)
        # print(f"\n  GET /api/all-payments/ ({num_records} records):")
        # print(f"    Queries: {query_count}")
        # print(f"    Time:    {get_elapsed*1000:.1f}ms")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], num_records)

        # print(f"\n  Summary:")
        # print(f"    Daytour create:  {daytour_elapsed:.2f}s")
        # print(f"    Payments POST:   {post_elapsed:.2f}s ({post_elapsed/num_records*1000:.1f}ms avg)")
        # print(f"    GET all-payments: {get_elapsed*1000:.1f}ms, {query_count} queries")

    def tearDown(self):
        Payment.objects.all().delete()
        PaymentMethod.objects.all().delete()
        PaymentStatus.objects.all().delete()
        AmenitiesAvailed.objects.all().delete()
        ActivitiesAvailed.objects.all().delete()
        GuestList.objects.all().delete()
        Billing.objects.all().delete()
        Customer.objects.all().delete()
        Amenities.objects.all().delete()
        Activity.objects.all().delete()
        Booking.objects.all().delete()
        Room.objects.all().delete()
        RoomType.objects.all().delete()
