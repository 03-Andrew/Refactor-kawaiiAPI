import time

from django.test import TestCase, override_settings
from django.db import connection, reset_queries

from rest_framework.test import APIClient

from bookings.models import Room, RoomType, RoomStatus
from transactions.models import (
    Amenities, AmenitiesAvailed, Activity, ActivitiesAvailed,
    Billing, Customer, GuestList, Payment, PaymentMethod,
    PaymentStatus,
)


@override_settings(DEBUG=True)
class ReportsNPlusOneTest(TestCase):
    """N+1 regression: report endpoints use PaymentSerializer without
    select_related or GenericForeignKey batch-prefetch.

    Daily/Weekly/Monthly/Yearly all serialize Payment querysets multiple
    times — each serialization triggers per-row FK + GFK queries.
    """

    def setUp(self):
        self.client = APIClient()

        # ── Shared reference data ──
        self.amenity = Amenities.objects.create(
            amenity="Boat Transfer", rate_per_head=500.00,
        )
        self.activity = Activity.objects.create(
            activity="Snorkeling", hourly_rate=300.00,
        )
        self.room_type = RoomType.objects.create(
            name="Standard", description="A standard room",
            price=2500.00, good_for=2, max_children=1, max_adult=2,
        )
        self.room = Room.objects.create(
            number="101", type=self.room_type, status=RoomStatus.AVAILABLE,
        )
        self.mop = PaymentMethod.objects.create(mode="GCash")
        self.payment_status = PaymentStatus.objects.create(status="Completed")

    # ── Helpers ────────────────────────────────────────────────

    def _create_daytour(self, email_suffix):
        """POST /api/bookings/daytour/ — returns billing data."""
        payload = {
            "customer": {
                "first_name": f"Rpt{email_suffix}",
                "last_name": "Test",
                "contact_number": "09111111111",
                "email": f"rpt{email_suffix}@test.com",
            },
            "guest_list": [f"Guest {email_suffix}"],
            "selected_amenities": [{"id": self.amenity.id, "head_count": 2}],
            "selected_activities": [{"id": self.activity.id, "hours": 2}],
        }
        response = self.client.post(
            "/api/bookings/daytour/", payload, format="json",
        )
        self.assertEqual(response.status_code, 201,
                         f"Daytour failed: {response.data}")
        return response.data

    def _create_payment(self, customer_bill_id, amenity_id, date_str="2026-07-28"):
        """POST /api/payment/multiple/ — pay for amenity."""
        payload = {
            "customerInfo": {
                "customer_bill": customer_bill_id,
                "date": date_str,
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

    def _seed_data(self, count=50):
        """Create `count` daytour bookings + payments. Returns year used."""
        # print(f"  Seeding {count} daytours + payments...")
        start = time.perf_counter()
        for i in range(count):
            data = self._create_daytour(i)
            billing_id = data["billing"]["id"]
            amenity_id = AmenitiesAvailed.objects.filter(
                customer_bill=billing_id,
            ).first().id
            self._create_payment(billing_id, amenity_id)
        elapsed = time.perf_counter() - start
        # print(f"  Seed complete: {count} records in {elapsed:.2f}s")
        self.assertEqual(Payment.objects.count(), count)

    # ── Report tests ──────────────────────────────────────────

    def test_daily_report(self):
        """GET /api/reports/daily/?date=YYYY-MM-DD — single day."""
        self._seed_data(50)

        date_str = "2026-07-28"
        reset_queries()

        start = time.perf_counter()
        response = self.client.get(f"/api/reports/daily/?date={date_str}")
        elapsed = time.perf_counter() - start

        query_count = len(connection.queries)
        # print(f"\n  GET /api/reports/daily/?date={date_str}:")
        # print(f"    Queries: {query_count}")
        # print(f"    Time:    {elapsed*1000:.1f}ms")

        self.assertEqual(response.status_code, 200)

    def test_weekly_report(self):
        """GET /api/reports/weekly/?year=2026&s=30&e=30 — one week.

        This is the heaviest: PaymentSerializer called per day (7x).
        """
        self._seed_data(50)

        reset_queries()

        start = time.perf_counter()
        response = self.client.get("/api/reports/weekly/?year=2026&s=30&e=30")
        elapsed = time.perf_counter() - start

        query_count = len(connection.queries)
        # print(f"\n  GET /api/reports/weekly/?year=2026&s=30&e=30:")
        # print(f"    Queries: {query_count}")
        # print(f"    Time:    {elapsed*1000:.1f}ms")

        self.assertEqual(response.status_code, 200)

    def test_monthly_report(self):
        """GET /api/reports/monthly/?year=2026&s=7 — one month."""
        self._seed_data(50)

        reset_queries()

        start = time.perf_counter()
        response = self.client.get("/api/reports/monthly/?year=2026&s=7")
        elapsed = time.perf_counter() - start

        query_count = len(connection.queries)
        # print(f"\n  GET /api/reports/monthly/?year=2026&s=7:")
        # print(f"    Queries: {query_count}")
        # print(f"    Time:    {elapsed*1000:.1f}ms")

        self.assertEqual(response.status_code, 200)

    def test_yearly_report(self):
        """GET /api/reports/yearly/?s=2026 — one year, all months."""
        self._seed_data(50)

        reset_queries()

        start = time.perf_counter()
        response = self.client.get("/api/reports/yearly/?s=2026")
        elapsed = time.perf_counter() - start

        query_count = len(connection.queries)
        # print(f"\n  GET /api/reports/yearly/?s=2026:")
        # print(f"    Queries: {query_count}")
        # print(f"    Time:    {elapsed*1000:.1f}ms")

        self.assertEqual(response.status_code, 200)

    def test_total_per_month(self):
        """GET /api/reports/monthly-total/?year=2026 — aggregation, no N+1 expected."""
        self._seed_data(50)

        reset_queries()

        start = time.perf_counter()
        response = self.client.get("/api/reports/monthly-total/?year=2026")
        elapsed = time.perf_counter() - start

        query_count = len(connection.queries)
        # print(f"\n  GET /api/reports/monthly-total/?year=2026:")
        # print(f"    Queries: {query_count}")
        # print(f"    Time:    {elapsed*1000:.1f}ms")

        self.assertEqual(response.status_code, 200)
        self.assertIn("months", response.data)
        self.assertEqual(len(response.data["months"]), 12)

    def test_all_reports_summary(self):
        """Run all reports and print summary comparison."""
        self._seed_data(50)

        endpoints = {
            "daily": "/api/reports/daily/?date=2026-07-28",
            "weekly": "/api/reports/weekly/?year=2026&s=30&e=30",
            "monthly": "/api/reports/monthly/?year=2026&s=7",
            "yearly": "/api/reports/yearly/?s=2026",
            "monthly-total": "/api/reports/monthly-total/?year=2026",
        }

        results = {}
        for label, url in endpoints.items():
            reset_queries()
            start = time.perf_counter()
            response = self.client.get(url)
            elapsed = time.perf_counter() - start
            query_count = len(connection.queries)
            self.assertEqual(response.status_code, 200)
            results[label] = (query_count, elapsed * 1000)

        # print(f"\n  {'Endpoint':<18} {'Queries':>8} {'Time':>10}")
        # print(f"  {'─'*18} {'─'*8} {'─'*10}")
        # for label, (qc, ms) in results.items():
        #     print(f"  {label:<18} {qc:>8} {ms:>8.1f}ms")

    # ── Cleanup ───────────────────────────────────────────────

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
        Room.objects.all().delete()
        RoomType.objects.all().delete()
