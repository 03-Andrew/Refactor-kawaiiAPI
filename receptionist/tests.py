"""
Receptionist Performance, Query Count, and Memory Tests
========================================================
Tests for:
- GET /api/amenities-availed/ vs GET /api/v0/amenities-availed/
- GET /api/activities-availed/ vs GET /api/v0/activities-availed/
- GET /api/all-payments/ vs GET /api/v0/all-payments/

Validates:
- Optimized (select_related & prefetch_related) vs v0 (Unoptimized)
- Query count, response time, and memory footprint
- Detailed summary table at the end of the test run
"""

import atexit
import time
import tracemalloc
from datetime import date, timedelta
from decimal import Decimal
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import AccessToken

from bookings.models import Booking, Room, RoomType, BookingStatus, RoomStatus
from transactions.models import (
    Amenities, AmenitiesAvailed, Activity, ActivitiesAvailed,
    Billing, Customer, FoodBill, AdditionalPayment, Payment, PaymentMethod,
    PaymentStatus, PaymentForChoices, BillingStatus
)

User = get_user_model()

RECEPTIONIST_BENCHMARK_RESULTS = []


def print_receptionist_summary_table():
    if not RECEPTIONIST_BENCHMARK_RESULTS:
        return

    header = f"{'Endpoint / Scenario':<42} | {'Version':<18} | {'Queries':<9} | {'Time (ms)':<11} | {'Mem Delta':<11} | {'Peak Mem':<11}"
    separator = "-" * len(header)
    title = "RECEPTIONIST PERFORMANCE & QUERY BENCHMARK SUMMARY"

    lines = [
        "",
        "=" * len(header),
        f"{title:^{len(header)}}",
        "=" * len(header),
        header,
        separator,
    ]

    for item in RECEPTIONIST_BENCHMARK_RESULTS:
        lines.append(
            f"{item['scenario']:<42} | {item['version']:<18} | {item['queries']:>9} | "
            f"{item['time_ms']:>9.2f} ms | {item['mem_delta']:>11} | {item['peak_mem']:>11}"
        )

    lines.append("=" * len(header))
    lines.append("")
    print("\n".join(lines))


atexit.register(print_receptionist_summary_table)


@override_settings(
    DEBUG=True,
    REST_FRAMEWORK={
        'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
        'PAGE_SIZE': 100,
        'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
        'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
        'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
        'DEFAULT_AUTHENTICATION_CLASSES': ['rest_framework_simplejwt.authentication.JWTAuthentication'],
        'DEFAULT_THROTTLE_CLASSES': [],
        'DEFAULT_THROTTLE_RATES': {},
    },
)
class ReceptionistPerformanceTestBase(TestCase):
    """Shared fixtures and helpers with bulk dataset generation."""

    TOTAL_RECORDS = 100

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="receptionist_testuser",
            password="testpassword123",
            role="RECEPTIONIST"
        )
        cls.token = str(AccessToken.for_user(cls.user))
        cls.auth_header = f"Bearer {cls.token}"

        cls.room_type = RoomType.objects.create(
            name="Standard Room",
            price=Decimal("2000.00"),
            max_adult=2,
        )
        cls.rooms = Room.objects.bulk_create([
            Room(number=f"R-{i}", type=cls.room_type, status=RoomStatus.AVAILABLE)
            for i in range(1, 11)
        ])
        cls.amenity = Amenities.objects.create(
            amenity="Boat Transfer",
            rate_per_head=Decimal("500.00"),
        )
        cls.activity = Activity.objects.create(
            activity="Snorkeling",
            hourly_rate=Decimal("300.00"),
        )
        cls.payment_method = PaymentMethod.objects.create(mode="GCash")
        cls.payment_status = PaymentStatus.objects.create(status="Completed")

        # Bulk create customers and billings
        customers = Customer.objects.bulk_create([
            Customer(
                first_name=f"Customer{i}",
                last_name=f"Recep{i}",
                contact_number="09111111111",
                email=f"customer_recep_{i}@test.com"
            )
            for i in range(cls.TOTAL_RECORDS)
        ])

        billings = Billing.objects.bulk_create([
            Billing(customer=customers[i], status=BillingStatus.PROCESSING)
            for i in range(cls.TOTAL_RECORDS)
        ])
        cls.billings = billings

        base_date = date(2026, 6, 1)
        Booking.objects.bulk_create([
            Booking(
                customer_bill=billings[i],
                room=cls.rooms[i % len(cls.rooms)],
                room_type=cls.room_type,
                check_in=base_date + timedelta(days=i * 2),
                check_out=base_date + timedelta(days=i * 2 + 1),
                adult_count=2,
                status=BookingStatus.APPROVED
            )
            for i in range(cls.TOTAL_RECORDS)
        ])

        FoodBill.objects.bulk_create([
            FoodBill(customer_bill=billings[i], price=Decimal("300.00"), or_number=f"OR-{i}")
            for i in range(cls.TOTAL_RECORDS)
        ])

        cls.amenities_availed = AmenitiesAvailed.objects.bulk_create([
            AmenitiesAvailed(
                customer_bill=billings[i],
                amenity=cls.amenity,
                head_count=2,
                time="10:00:00"
            )
            for i in range(cls.TOTAL_RECORDS)
        ])

        cls.activities_availed = ActivitiesAvailed.objects.bulk_create([
            ActivitiesAvailed(
                customer_bill=billings[i],
                activity=cls.activity,
                hours_availed=Decimal("2.00")
            )
            for i in range(cls.TOTAL_RECORDS)
        ])

        AdditionalPayment.objects.bulk_create([
            AdditionalPayment(
                customer_bill=billings[i],
                reason="Towel",
                price=Decimal("100.00")
            )
            for i in range(cls.TOTAL_RECORDS)
        ])

        now = timezone.now()
        cls.payments = Payment.objects.bulk_create([
            Payment(
                customer_bill=billings[i],
                amount=Decimal("1000.00"),
                date=now,
                mop=cls.payment_method,
                status=cls.payment_status,
                paymentFor=PaymentForChoices.AMENITIES,
                content_type_id=None,
                object_id=None,
            )
            for i in range(cls.TOTAL_RECORDS)
        ])

    def setUp(self):
        cache.clear()
        APIView.throttle_classes = []
        self.client = APIClient()

    def run_benchmark(self, url, scenario, version="Optimized"):
        """Runs a GET endpoint and records metrics."""
        tracemalloc.start()
        with CaptureQueriesContext(connection) as query_context:
            start_time = time.perf_counter()
            response = self.client.get(
                url,
                HTTP_AUTHORIZATION=self.auth_header
            )
            elapsed_time = time.perf_counter() - start_time
        current_mem, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        query_count = len(query_context)

        def format_bytes(b):
            if b >= 1024 * 1024:
                return f"{b / (1024 * 1024):.2f} MB"
            return f"{b / 1024:.2f} KB"

        RECEPTIONIST_BENCHMARK_RESULTS.append({
            "scenario": scenario,
            "version": version,
            "queries": f"{query_count:,}",
            "time_ms": elapsed_time * 1000,
            "mem_delta": format_bytes(current_mem),
            "peak_mem": format_bytes(peak_mem),
        })

        return response, query_count, elapsed_time, current_mem, peak_mem


class AmenitiesAvailedComparisonTest(ReceptionistPerformanceTestBase):
    """Compare GET /api/amenities-availed/ (Optimized) vs /api/v0/amenities-availed/ (Unoptimized)"""

    def test_amenities_availed_optimized_vs_v0(self):
        # 1. Before (v0 Unoptimized)
        res_v0, q_v0, t_v0, _, _ = self.run_benchmark(
            "/api/v0/amenities-availed/",
            f"GET /api/amenities-availed/ ({self.TOTAL_RECORDS} items)",
            "Before (v0)"
        )
        self.assertEqual(res_v0.status_code, 200)
        self.assertEqual(res_v0.data["count"], self.TOTAL_RECORDS)

        # 2. After (Optimized)
        res_opt, q_opt, t_opt, _, _ = self.run_benchmark(
            "/api/amenities-availed/",
            f"GET /api/amenities-availed/ ({self.TOTAL_RECORDS} items)",
            "After (Optimized)"
        )
        self.assertEqual(res_opt.status_code, 200)
        self.assertEqual(res_opt.data["count"], self.TOTAL_RECORDS)
        self.assertLessEqual(q_opt, 20)
        self.assertLess(t_opt, 0.5)

        # Optimized must execute dramatically fewer queries than v0
        self.assertLess(
            q_opt, q_v0,
            f"Optimized ({q_opt} queries) should be far fewer than v0 ({q_v0} queries)"
        )


class ActivitiesAvailedComparisonTest(ReceptionistPerformanceTestBase):
    """Compare GET /api/activities-availed/ (Optimized) vs /api/v0/activities-availed/ (Unoptimized)"""

    def test_activities_availed_optimized_vs_v0(self):
        # 1. Before (v0 Unoptimized)
        res_v0, q_v0, t_v0, _, _ = self.run_benchmark(
            "/api/v0/activities-availed/",
            f"GET /api/activities-availed/ ({self.TOTAL_RECORDS} items)",
            "Before (v0)"
        )
        self.assertEqual(res_v0.status_code, 200)
        self.assertEqual(res_v0.data["count"], self.TOTAL_RECORDS)

        # 2. After (Optimized)
        res_opt, q_opt, t_opt, _, _ = self.run_benchmark(
            "/api/activities-availed/",
            f"GET /api/activities-availed/ ({self.TOTAL_RECORDS} items)",
            "After (Optimized)"
        )
        self.assertEqual(res_opt.status_code, 200)
        self.assertEqual(res_opt.data["count"], self.TOTAL_RECORDS)
        self.assertLessEqual(q_opt, 20)
        self.assertLess(t_opt, 0.5)

        # Optimized must execute dramatically fewer queries than v0
        self.assertLess(
            q_opt, q_v0,
            f"Optimized ({q_opt} queries) should be far fewer than v0 ({q_v0} queries)"
        )


class PaymentsComparisonTest(ReceptionistPerformanceTestBase):
    """Compare GET /api/all-payments/ (Optimized) vs /api/v0/all-payments/ (Unoptimized)"""

    def test_payments_optimized_vs_v0(self):
        # 1. Before (v0 Unoptimized)
        res_v0, q_v0, t_v0, _, _ = self.run_benchmark(
            "/api/v0/all-payments/",
            f"GET /api/all-payments/ ({self.TOTAL_RECORDS} items)",
            "Before (v0)"
        )
        self.assertEqual(res_v0.status_code, 200)
        self.assertEqual(res_v0.data["count"], self.TOTAL_RECORDS)

        # 2. After (Optimized)
        res_opt, q_opt, t_opt, _, _ = self.run_benchmark(
            "/api/all-payments/",
            f"GET /api/all-payments/ ({self.TOTAL_RECORDS} items)",
            "After (Optimized)"
        )
        self.assertEqual(res_opt.status_code, 200)
        self.assertEqual(res_opt.data["count"], self.TOTAL_RECORDS)
        self.assertLessEqual(q_opt, 10)
        self.assertLess(t_opt, 0.5)

        # Optimized must execute fewer queries than v0
        self.assertLess(
            q_opt, q_v0,
            f"Optimized ({q_opt} queries) should be fewer than v0 ({q_v0} queries)"
        )
