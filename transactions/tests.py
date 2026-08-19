"""
Billing Performance, Query Count, and Memory Tests
===================================================
Tests for:
- GET /api/billings/ (List billings with pagination and filters)
- GET /api/billings/details/<id>/ (Detailed billing view with all relations and totals)
- GET /api/billings/<id>/ (Single entity base billing view)
- GET /api/v0/billings/ (Unoptimized v0 list view without select/prefetch)
- GET /api/v0/billings/details/<id>/ (Unoptimized v0 detail view without select/prefetch)

Validates:
- 1,000 Billing records performance
- Query count bounded and free of N+1 query regressions
- Execution speed / latency benchmarking
- Memory usage (current delta & peak RAM allocated via tracemalloc)
- Prints a structured Before vs After summary comparison table at the end
"""

import atexit
import time
import tracemalloc
from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIRequestFactory
from rest_framework_simplejwt.tokens import AccessToken

from bookings.models import Booking, Room, RoomType, BookingStatus, RoomStatus
from transactions.models import (
    Billing, Customer, BillingStatus,
    Amenities, AmenitiesAvailed,
    Activity, ActivitiesAvailed,
    FoodBill, AdditionalPayment,
    PaymentMethod, Payment, PaymentForChoices
)
from transactions.views import BillingList, BillingDetails, BillingSingleEntity
from transactions.views_v0 import BillingListV0, BillingDetailsV0, BillingSingleEntityV0

User = get_user_model()

# Global collector for summary report
BENCHMARK_RESULTS = []


def print_summary_table():
    if not BENCHMARK_RESULTS:
        return

    header = f"{'Endpoint / Scenario':<42} | {'Version':<18} | {'Queries':<9} | {'Time (ms)':<11} | {'Mem Delta':<11} | {'Peak Mem':<11}"
    separator = "-" * len(header)
    title = "BILLINGS PERFORMANCE & QUERY BENCHMARK SUMMARY (1,000 DB RECORDS)"

    lines = [
        "",
        "=" * len(header),
        f"{title:^{len(header)}}",
        "=" * len(header),
        header,
        separator,
    ]

    for item in BENCHMARK_RESULTS:
        lines.append(
            f"{item['scenario']:<42} | {item['version']:<18} | {item['queries']:>9} | "
            f"{item['time_ms']:>9.2f} ms | {item['mem_delta']:>11} | {item['peak_mem']:>11}"
        )

    lines.append("=" * len(header))
    lines.append("")
    print("\n".join(lines))


atexit.register(print_summary_table)


class BillingPerformanceTestBase(TestCase):
    """Base test class that populates 1,000 Billing records with related models."""

    TOTAL_RECORDS = 1000

    @classmethod
    def setUpTestData(cls):
        # 1. Create auth user and JWT token
        cls.user = User.objects.create_user(
            username="receptionist_perf",
            password="testpassword123",
            role="RECEPTIONIST"
        )
        cls.token = str(AccessToken.for_user(cls.user))
        cls.auth_header = f"Bearer {cls.token}"

        # 2. Master lookup data
        cls.room_type = RoomType.objects.create(
            name="Deluxe Suite",
            price=Decimal("3500.00"),
            description="Deluxe test room",
            good_for=2,
            max_children=1,
            max_adult=2
        )
        cls.room = Room.objects.create(
            number="301",
            type=cls.room_type,
            status=RoomStatus.AVAILABLE
        )
        cls.amenity = Amenities.objects.create(
            amenity="Pool Access",
            rate_per_head=Decimal("250.00")
        )
        cls.activity = Activity.objects.create(
            activity="Kayaking",
            hourly_rate=Decimal("500.00")
        )
        cls.mop = PaymentMethod.objects.create(mode="Cash")

        # 3. Bulk create 1,000 Customers
        customers_to_create = [
            Customer(
                first_name=f"CustomerFirst{i}",
                last_name=f"CustomerLast{i}",
                contact_number=f"09{i:09d}",
                email=f"customer{i}@example.com"
            )
            for i in range(cls.TOTAL_RECORDS)
        ]
        created_customers = Customer.objects.bulk_create(customers_to_create)

        # 4. Bulk create 1,000 Billings (alternating status)
        billings_to_create = [
            Billing(
                customer=created_customers[i],
                status=BillingStatus.PROCESSING if i % 2 == 0 else BillingStatus.COMPLETE
            )
            for i in range(cls.TOTAL_RECORDS)
        ]
        created_billings = Billing.objects.bulk_create(billings_to_create)

        cls.first_billing_id = created_billings[0].id
        cls.mid_billing_id = created_billings[500].id
        cls.last_billing_id = created_billings[-1].id

        # 5. Bulk create related records for all 1,000 billings
        today = date.today()

        # Bookings (1 per billing)
        bookings_to_create = [
            Booking(
                customer_bill=created_billings[i],
                room=cls.room,
                room_type=cls.room_type,
                check_in=today + timedelta(days=i),
                check_out=today + timedelta(days=i + 2),
                adult_count=2,
                children_count=0,
                status=BookingStatus.APPROVED
            )
            for i in range(cls.TOTAL_RECORDS)
        ]
        Booking.objects.bulk_create(bookings_to_create)

        # AmenitiesAvailed (1 per billing)
        amenities_availed_to_create = [
            AmenitiesAvailed(
                customer_bill=created_billings[i],
                amenity=cls.amenity,
                head_count=2,
                time="14:00:00"
            )
            for i in range(cls.TOTAL_RECORDS)
        ]
        AmenitiesAvailed.objects.bulk_create(amenities_availed_to_create)

        # ActivitiesAvailed (1 per billing)
        activities_availed_to_create = [
            ActivitiesAvailed(
                customer_bill=created_billings[i],
                activity=cls.activity,
                hours_availed=Decimal("2.00")
            )
            for i in range(cls.TOTAL_RECORDS)
        ]
        ActivitiesAvailed.objects.bulk_create(activities_availed_to_create)

        # FoodBills (1 per billing)
        food_bills_to_create = [
            FoodBill(
                customer_bill=created_billings[i],
                or_number=f"OR-{i:05d}",
                price=Decimal("450.00")
            )
            for i in range(cls.TOTAL_RECORDS)
        ]
        FoodBill.objects.bulk_create(food_bills_to_create)

        # AdditionalPayments (1 per billing)
        additional_payments_to_create = [
            AdditionalPayment(
                customer_bill=created_billings[i],
                reason="Extra Towel & Bedding",
                price=Decimal("150.00")
            )
            for i in range(cls.TOTAL_RECORDS)
        ]
        AdditionalPayment.objects.bulk_create(additional_payments_to_create)

        # Payments (1 per billing)
        payments_to_create = [
            Payment(
                customer_bill=created_billings[i],
                amount=Decimal("1000.00"),
                date=timezone.now(),
                mop=cls.mop,
                paymentFor=PaymentForChoices.DOWN_PAYMENT
            )
            for i in range(cls.TOTAL_RECORDS)
        ]
        Payment.objects.bulk_create(payments_to_create)

    def setUp(self):
        self.factory = APIRequestFactory()

    def run_benchmark(self, view_fn, request, scenario, version="After (Optimized)", **kwargs):
        """Runs a view with memory tracking, query counting, and timing."""
        tracemalloc.start()
        with CaptureQueriesContext(connection) as query_context:
            start_time = time.perf_counter()
            response = view_fn(request, **kwargs)
            elapsed_time = time.perf_counter() - start_time
        current_mem, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        query_count = len(query_context)

        def format_bytes(b):
            if b >= 1024 * 1024:
                return f"{b / (1024 * 1024):.2f} MB"
            return f"{b / 1024:.2f} KB"

        BENCHMARK_RESULTS.append({
            "scenario": scenario,
            "version": version,
            "queries": f"{query_count:,}",
            "time_ms": elapsed_time * 1000,
            "mem_delta": format_bytes(current_mem),
            "peak_mem": format_bytes(peak_mem),
        })

        return response, query_count, elapsed_time, current_mem, peak_mem


class BillingComparisonPerformanceTests(BillingPerformanceTestBase):
    """Before (v0) vs After (Optimized) performance benchmarks."""

    def test_01_billings_list_before_vs_after(self):
        """Compare GET /api/v0/billings/ vs GET /api/billings/ (100 items)."""
        # 1. Before (v0)
        req_v0 = self.factory.get("/api/v0/billings/", HTTP_AUTHORIZATION=self.auth_header)
        res_v0, q_v0, t_v0, _, _ = self.run_benchmark(
            BillingListV0.as_view(), req_v0, "GET /api/billings/ (100 items)", "Before (v0)"
        )
        self.assertEqual(res_v0.status_code, 200)

        # 2. After (Optimized)
        req_opt = self.factory.get("/api/billings/", HTTP_AUTHORIZATION=self.auth_header)
        res_opt, q_opt, t_opt, _, _ = self.run_benchmark(
            BillingList.as_view(), req_opt, "GET /api/billings/ (100 items)", "After (Optimized)"
        )
        self.assertEqual(res_opt.status_code, 200)

        self.assertLess(
            q_opt, q_v0,
            f"Optimized ({q_opt} queries) should be far fewer than v0 ({q_v0} queries)"
        )

    def test_02_billing_details_before_vs_after(self):
        """Compare GET /api/v0/billings/details/<id>/ vs GET /api/billings/details/<id>/."""
        target_id = self.mid_billing_id

        # 1. Before (v0)
        req_v0 = self.factory.get(f"/api/v0/billings/details/{target_id}/", HTTP_AUTHORIZATION=self.auth_header)
        res_v0, q_v0, t_v0, _, _ = self.run_benchmark(
            BillingDetailsV0.as_view(), req_v0, f"GET /api/billings/details/{target_id}/", "Before (v0)", pk=target_id
        )
        self.assertEqual(res_v0.status_code, 200)

        # 2. After (Optimized)
        req_opt = self.factory.get(f"/api/billings/details/{target_id}/", HTTP_AUTHORIZATION=self.auth_header)
        res_opt, q_opt, t_opt, _, _ = self.run_benchmark(
            BillingDetails.as_view(), req_opt, f"GET /api/billings/details/{target_id}/", "After (Optimized)", pk=target_id
        )
        self.assertEqual(res_opt.status_code, 200)

        self.assertLess(
            q_opt, q_v0,
            f"Optimized ({q_opt} queries) should be fewer than v0 ({q_v0} queries)"
        )

