"""
Reports Performance, Query Count, and Memory Tests
===================================================
Tests for:
- GET /api/reports/daily/ vs GET /api/v0/reports/daily/
- GET /api/reports/weekly/ vs GET /api/v0/reports/weekly/
- GET /api/reports/monthly/ vs GET /api/v0/reports/monthly/
- GET /api/reports/yearly/ vs GET /api/v0/reports/yearly/
- GET /api/reports/monthly-total/ vs GET /api/v0/reports/monthly-total/

Validates:
- Optimized (select_related, GFK batch-prefetch & range queries) vs v0 (Unoptimized)
- Query count, response time, and memory footprint via tracemalloc
- Prints a structured comparison summary table at the end
"""

import atexit
import time
import tracemalloc
from datetime import date, datetime, timedelta
from decimal import Decimal
from django.test import TestCase, override_settings
from django.db import connection
from django.utils import timezone
from django.test.utils import CaptureQueriesContext
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from bookings.models import Room, RoomType, Booking, RoomStatus, BookingStatus
from transactions.models import (
    Amenities, AmenitiesAvailed, Activity, ActivitiesAvailed,
    Billing, Customer, Payment, PaymentMethod, PaymentStatus,
    PaymentForChoices, BillingStatus
)

User = get_user_model()

REPORTS_BENCHMARK_RESULTS = []


def print_reports_summary_table():
    if not REPORTS_BENCHMARK_RESULTS:
        return

    header = f"{'Endpoint / Scenario':<42} | {'Version':<18} | {'Queries':<9} | {'Time (ms)':<11} | {'Mem Delta':<11} | {'Peak Mem':<11}"
    separator = "-" * len(header)
    title = "REPORTS PERFORMANCE & QUERY BENCHMARK SUMMARY"

    lines = [
        "",
        "=" * len(header),
        f"{title:^{len(header)}}",
        "=" * len(header),
        header,
        separator,
    ]

    for item in REPORTS_BENCHMARK_RESULTS:
        lines.append(
            f"{item['scenario']:<42} | {item['version']:<18} | {item['queries']:>9} | "
            f"{item['time_ms']:>9.2f} ms | {item['mem_delta']:>11} | {item['peak_mem']:>11}"
        )

    lines.append("=" * len(header))
    lines.append("")
    print("\n".join(lines))


atexit.register(print_reports_summary_table)


@override_settings(DEBUG=True)
class ReportsPerformanceTest(TestCase):
    """Benchmark tests comparing optimized report views vs v0 unoptimized report views."""

    RECORD_COUNT = 50

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="report_admin", password="adminpassword123", role="ADMIN"
        )
        cls.token = str(AccessToken.for_user(cls.user))
        cls.auth_header = f"Bearer {cls.token}"

        # Reference Models
        cls.room_type = RoomType.objects.create(
            name="Deluxe Suite",
            price=Decimal("2500.00"),
            max_adult=2,
            good_for=2,
        )
        cls.room = Room.objects.create(
            number="101", type=cls.room_type, status=RoomStatus.AVAILABLE
        )
        cls.amenity = Amenities.objects.create(
            amenity="Boat Transfer", rate_per_head=Decimal("500.00")
        )
        cls.activity = Activity.objects.create(
            activity="Snorkeling", hourly_rate=Decimal("300.00")
        )
        cls.mop = PaymentMethod.objects.create(mode="GCash")
        cls.payment_status = PaymentStatus.objects.create(status="Completed")

        # Content Types for GenericForeignKey
        cls.ct_amenity = ContentType.objects.get_for_model(AmenitiesAvailed)
        cls.ct_activity = ContentType.objects.get_for_model(ActivitiesAvailed)
        cls.ct_booking = ContentType.objects.get_for_model(Booking)

        # Bulk seed 50 customers and billings
        customers = Customer.objects.bulk_create([
            Customer(
                first_name=f"ReportFirst{i}",
                last_name=f"ReportLast{i}",
                contact_number="09111111111",
                email=f"report{i}@example.com"
            )
            for i in range(cls.RECORD_COUNT)
        ])

        billings = Billing.objects.bulk_create([
            Billing(customer=customers[i], status=BillingStatus.PROCESSING)
            for i in range(cls.RECORD_COUNT)
        ])

        # Amenities availed
        amenities_availed = AmenitiesAvailed.objects.bulk_create([
            AmenitiesAvailed(
                customer_bill=billings[i],
                amenity=cls.amenity,
                head_count=2,
                time="10:00:00"
            )
            for i in range(cls.RECORD_COUNT)
        ])

        # Payments spread across date ranges (2026-07-28 in Week 31, Month 7, Year 2026)
        base_date = timezone.make_aware(datetime(2026, 7, 28, 12, 0, 0))
        Payment.objects.bulk_create([
            Payment(
                customer_bill=billings[i],
                amount=Decimal("1000.00"),
                date=base_date + timedelta(days=(i % 5)),
                mop=cls.mop,
                status=cls.payment_status,
                paymentFor=PaymentForChoices.AMENITIES,
                content_type=cls.ct_amenity,
                object_id=amenities_availed[i].id,
            )
            for i in range(cls.RECORD_COUNT)
        ])

    def setUp(self):
        self.client = APIClient()

    def run_benchmark(self, url, scenario, version="Optimized"):
        """Runs a GET endpoint and captures queries, time, and memory."""
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

        REPORTS_BENCHMARK_RESULTS.append({
            "scenario": scenario,
            "version": version,
            "queries": f"{query_count:,}",
            "time_ms": elapsed_time * 1000,
            "mem_delta": format_bytes(current_mem),
            "peak_mem": format_bytes(peak_mem),
        })

        return response, query_count, elapsed_time, current_mem, peak_mem

    def test_daily_report_optimized_vs_v0(self):
        """Compare GET /api/reports/daily/ vs GET /api/v0/reports/daily/"""
        # 1. Before (v0 Unoptimized)
        res_v0, q_v0, t_v0, _, _ = self.run_benchmark(
            "/api/v0/reports/daily/?date=2026-07-28",
            "GET /api/reports/daily/",
            "Before (v0)"
        )
        self.assertEqual(res_v0.status_code, 200)

        # 2. After (Optimized)
        res_opt, q_opt, t_opt, _, _ = self.run_benchmark(
            "/api/reports/daily/?date=2026-07-28",
            "GET /api/reports/daily/",
            "After (Optimized)"
        )
        self.assertEqual(res_opt.status_code, 200)

        self.assertLess(
            q_opt, q_v0,
            f"Optimized daily report queries ({q_opt}) should be fewer than v0 ({q_v0})"
        )

    def test_weekly_report_optimized_vs_v0(self):
        """Compare GET /api/reports/weekly/ vs GET /api/v0/reports/weekly/"""
        # 1. Before (v0 Unoptimized)
        res_v0, q_v0, t_v0, _, _ = self.run_benchmark(
            "/api/v0/reports/weekly/?year=2026&s=30&e=30",
            "GET /api/reports/weekly/ (1 week)",
            "Before (v0)"
        )
        self.assertEqual(res_v0.status_code, 200)

        # 2. After (Optimized)
        res_opt, q_opt, t_opt, _, _ = self.run_benchmark(
            "/api/reports/weekly/?year=2026&s=30&e=30",
            "GET /api/reports/weekly/ (1 week)",
            "After (Optimized)"
        )
        self.assertEqual(res_opt.status_code, 200)

        self.assertLess(
            q_opt, q_v0,
            f"Optimized weekly report queries ({q_opt}) should be fewer than v0 ({q_v0})"
        )

    def test_monthly_report_optimized_vs_v0(self):
        """Compare GET /api/reports/monthly/ vs GET /api/v0/reports/monthly/"""
        # 1. Before (v0 Unoptimized)
        res_v0, q_v0, t_v0, _, _ = self.run_benchmark(
            "/api/v0/reports/monthly/?year=2026&s=7&e=7",
            "GET /api/reports/monthly/ (1 month)",
            "Before (v0)"
        )
        self.assertEqual(res_v0.status_code, 200)

        # 2. After (Optimized)
        res_opt, q_opt, t_opt, _, _ = self.run_benchmark(
            "/api/reports/monthly/?year=2026&s=7&e=7",
            "GET /api/reports/monthly/ (1 month)",
            "After (Optimized)"
        )
        self.assertEqual(res_opt.status_code, 200)

        self.assertLess(
            q_opt, q_v0,
            f"Optimized monthly report queries ({q_opt}) should be fewer than v0 ({q_v0})"
        )

    def test_yearly_report_optimized_vs_v0(self):
        """Compare GET /api/reports/yearly/ vs GET /api/v0/reports/yearly/"""
        # 1. Before (v0 Unoptimized)
        res_v0, q_v0, t_v0, _, _ = self.run_benchmark(
            "/api/v0/reports/yearly/?s=2026&e=2026",
            "GET /api/reports/yearly/ (1 year)",
            "Before (v0)"
        )
        self.assertEqual(res_v0.status_code, 200)

        # 2. After (Optimized)
        res_opt, q_opt, t_opt, _, _ = self.run_benchmark(
            "/api/reports/yearly/?s=2026&e=2026",
            "GET /api/reports/yearly/ (1 year)",
            "After (Optimized)"
        )
        self.assertEqual(res_opt.status_code, 200)

        self.assertLess(
            q_opt, q_v0,
            f"Optimized yearly report queries ({q_opt}) should be fewer than v0 ({q_v0})"
        )

    def test_monthly_total_optimized_vs_v0(self):
        """Compare GET /api/reports/monthly-total/ vs GET /api/v0/reports/monthly-total/"""
        # 1. Before (v0 Unoptimized)
        res_v0, q_v0, t_v0, _, _ = self.run_benchmark(
            "/api/v0/reports/monthly-total/?year=2026",
            "GET /api/reports/monthly-total/",
            "Before (v0)"
        )
        self.assertEqual(res_v0.status_code, 200)

        # 2. After (Optimized)
        res_opt, q_opt, t_opt, _, _ = self.run_benchmark(
            "/api/reports/monthly-total/?year=2026",
            "GET /api/reports/monthly-total/",
            "After (Optimized)"
        )
        self.assertEqual(res_opt.status_code, 200)

        self.assertEqual(res_opt.data, res_v0.data)
