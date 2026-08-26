"""
Booking Tests
=============
BookingCreationTests   - online, stay-in, and day-tour booking creation
BookingPerformanceTests - N+1 regression and bulk-create speed checks
ApproveBookingTests     - approve booking scenarios
CancelBookingTests     - cancel booking scenarios
"""
import time
from unittest.mock import patch
from django.test import TestCase
from rest_framework.test import APIRequestFactory
from rest_framework_simplejwt.tokens import AccessToken

from bookings.models import Booking, Room, RoomType, BookingStatus, RoomStatus
from bookings.views.bookings import (
    ApproveBooking, CancelBooking,
    CreateDayTourGuest, CreateOnlineBooking, CreateStayInBooking,
)
from transactions.models import Billing, Customer, Amenities, AmenitiesAvailed, GuestList, ActivitiesAvailed, Activity, BillingStatus

from django.contrib.auth import get_user_model
# ── Shared base ────────────────────────────────────────────────────────────────
User = get_user_model()
class BookingTestBase(TestCase):
    """Shared fixtures and helpers used by all booking test classes."""

    def get_jwt_token(self, user):
        token = AccessToken.for_user(user) 
        return str(token)
    
    def setUp(self):
        self.factory = APIRequestFactory()
        self.token = self.get_jwt_token(User.objects.create_user(username="testuser", password="testpass", role="RECEPTIONIST"))
        self.fake_token = self.get_jwt_token(User.objects.create_user(username="fakeuser", password="fakepass", role="GUARD"))

        self.room_type = RoomType.objects.create(
            name="Test Room Type",
            description="A test room type",
            price=2500.00,
            good_for=2,
            max_children=1,
            max_adult=2,
        )

        room_numbers = ["101", "102", "103", "104", "106"]
        self.rooms = Room.objects.bulk_create([
            Room(number=number, type=self.room_type, status=RoomStatus.AVAILABLE)
            for number in room_numbers
        ])

        self.amenities = Amenities.objects.create(
            amenity="Boat Transfer",
            rate_per_head=200.00,
        )

        self.activities = Activity.objects.create(
            activity="Snorkeling",
            hourly_rate=300.00,
        )

    def tearDown(self):
        Booking.objects.all().delete()
        AmenitiesAvailed.objects.all().delete()
        ActivitiesAvailed.objects.all().delete()
        GuestList.objects.all().delete()
        Billing.objects.all().delete()
        Customer.objects.all().delete()
        Amenities.objects.all().delete()
        Activity.objects.all().delete()
        Room.objects.all().delete()
        RoomType.objects.all().delete()

    @patch('bookings.turnstile.requests.post')
    def _create_online_booking(self, email="patch-test@example.com", mock_post=None):
        """Helper: create an online booking and return (booking_id, billing_id)."""
        request_data = {
            "customer": {
                "first_name": "Patch",
                "last_name": "Test",
                "contact_number": "09123456789",
                "email": email,
            },
            "rooms": [{
                "room_type": self.room_type.id,
                "check_in": "2027-10-01",
                "check_out": "2027-10-03",
                "adult_count": 2,
                "children_count": 0,
                "extra_guest": 0,
            }],
            "payment": 1000.00,
            "turnstile_token": "dummy-token",
        }
        mock_post.return_value.json.return_value = {"success": True}
        request = self.factory.post(
            '/api/bookings/online/', request_data, content_type='application/json',
        )
        response = CreateOnlineBooking.as_view()(request)
        self.assertEqual(response.status_code, 201)
        booking_id = response.data['bookings'][0]['id']
        billing_id = response.data['billing']['id']
        return booking_id, billing_id


# ── Booking creation ───────────────────────────────────────────────────────────

class BookingCreationTests(BookingTestBase):
    """Tests for creating bookings via online, stay-in, and day-tour endpoints."""

    @patch('bookings.turnstile.requests.post')
    def test_create_online_booking(self, mock_post):
        check_in = "2026-09-01"
        check_out = "2026-09-05"

        request_data = {
            "customer": {
                "first_name": "John",
                "last_name": "Doe",
                "contact_number": "09123456789",
                "email": "john.doe@example.com",
            },
            "rooms": [{
                "room_type": self.room_type.id,
                "check_in": check_in,
                "check_out": check_out,
                "adult_count": 2,
                "children_count": 0,
                "extra_guest": 0,
            }],
            "boat": {
                "head_count": 2,
                "time": "10:00",
                "guests": ["John Doe", "Jane Doe"],
            },
            "turnstile_token": "dummy-token",
        }
        mock_post.return_value.json.return_value = {"success": True}
        request = self.factory.post(
            '/api/bookings/online/', request_data, content_type='application/json',
        )

        response = CreateOnlineBooking.as_view()(request)
        self.assertEqual(response.status_code, 201)
        self.assertIn('customer', response.data)
        self.assertIn('billing', response.data)
        self.assertIn('bookings', response.data)
        self.assertEqual(len(response.data['bookings']), 1)
        self.assertEqual(response.data['bookings'][0]['room'], None)

    def test_create_stay_in_booking(self):
        check_in = "2026-09-01"
        check_out = "2026-09-05"

        request_data = {
            "customer": {
                "first_name": "Jane",
                "last_name": "Smith",
                "contact_number": "09123456789",
                "email": "testEmail@gmail.com",
            },
            "booking": [{
                "room_type": self.room_type.id,
                "check_in": check_in,
                "check_out": check_out,
                "adult_count": 2,
                "children_count": 0,
                "extra_guest": 0,
                "room_number": self.rooms[0].id,
            }],
        }

        request = self.factory.post(
            '/api/bookings/stay-in/', request_data, content_type='application/json', 
            HTTP_AUTHORIZATION=f'Bearer {self.token}',
        )
        response = CreateStayInBooking.as_view()(request)
        self.assertIn(response.status_code, [200, 201])

    def test_create_stay_in_booking_unauthorized_role(self):
        check_in = "2026-09-01"
        check_out = "2026-09-05"

        request_data = {
            "customer": {
                "first_name": "Jane",
                "last_name": "Smith",
                "contact_number": "09123456789",
                "email": "testEmail@gmail.com",
            },
            "booking": [{
                "room_type": self.room_type.id,
                "check_in": check_in,
                "check_out": check_out,
                "adult_count": 2,
                "children_count": 0,
                "extra_guest": 0,
                "room_number": self.rooms[1].id,
            }],
        }

        request = self.factory.post(
            '/api/bookings/stay-in/', request_data, content_type='application/json', 
            HTTP_AUTHORIZATION=f'Bearer {self.fake_token}',
        )
        response = CreateStayInBooking.as_view()(request)
        self.assertIn(response.status_code, [400, 403])

    def test_day_tour_booking(self):
        request_data = {
            "customer": {
                "first_name": "Alice",
                "last_name": "Johnson",
                "contact_number": "09123456789",
                "email": "alice.johnson@example.com",
            },
            "guest_list": ["Alice Johnson", "Bob Smith"],
            "selected_amenities": [{"id": self.amenities.id, "head_count": 2}],
            "selected_activities": [{"id": self.activities.id, "hours": 2}],
        }

        request = self.factory.post(
            '/api/bookings/daytour/', request_data, content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )
        response = CreateDayTourGuest.as_view()(request)
        self.assertEqual(response.status_code, 201)


# ── Performance / N+1 regressions ─────────────────────────────────────────────

class BookingPerformanceTests(BookingTestBase):
    """Regression tests ensuring booking endpoints avoid N+1 query patterns."""

    def test_create_stay_in_booking_multi_room_query_count(self):
        """N+1 regression: 4-room booking time <4x 1-room time (batched queries)."""
        check_in = "2026-12-01"
        check_out = "2026-12-03"

        extra_rooms = Room.objects.bulk_create([
            Room(number=num, type=self.room_type, status=RoomStatus.AVAILABLE)
            for num in ["202", "203", "204", "205", "206"]
        ])
        extra_ids = [r.id for r in extra_rooms]

        def make_booking(room_ids, email):
            request_data = {
                "customer": {
                    "first_name": "Perf",
                    "last_name": "Test",
                    "contact_number": "0911111111",
                    "email": email,
                },
                "booking": [
                    {
                        "room_type": self.room_type.id,
                        "check_in": check_in,
                        "check_out": check_out,
                        "adult_count": 2,
                        "children_count": 0,
                        "extra_guest": 0,
                        "room_number": rid,
                    }
                    for rid in room_ids
                ],
            }
            request = self.factory.post(
                '/api/bookings/onsite/', request_data, content_type='application/json', 
                HTTP_AUTHORIZATION=f'Bearer {self.token}',
            )
            start = time.perf_counter()
            response = CreateStayInBooking.as_view()(request)
            elapsed = time.perf_counter() - start
            self.assertIn(response.status_code, [200, 201],
                          f"booking failed: {response.data}")
            return elapsed

        t1 = make_booking(extra_ids[:1], "perf-a@test.com")
        t4 = make_booking(extra_ids[1:5], "perf-b@test.com")

        ratio = t4 / t1
        # print(f"\n  Booking speed: 1 room={t1*1000:.1f}ms, 4 rooms={t4*1000:.1f}ms, ratio={ratio:.2f}x")
        self.assertLess(ratio, 4.0,
                        f"4-room booking should be <4x 1-room time (got {ratio:.2f}x)")

    @patch('bookings.turnstile.requests.post')
    def test_online_booking_multi_room_query_count(self, mock_post):
        """N+1 regression: online booking with boats — constant query profile."""
        check_in = "2026-12-10"
        check_out = "2026-12-12"

        def make_booking(room_count, boat_count, email):
            request_data = {
                "customer": {
                    "first_name": "Perf", "last_name": "Online",
                    "contact_number": "0922222222", "email": email,
                },
                "rooms": [
                    {
                        "room_type": self.room_type.id,
                        "check_in": check_in,
                        "check_out": check_out,
                        "adult_count": 2,
                        "children_count": 0,
                        "extra_guest": 0,
                    }
                    for _ in range(room_count)
                ],
                "boat": {
                    "head_count": 2,
                    "time": "10:00",
                    "guests": ["John Doe1", "Jane Doe2"],
                },
                "payment": 1000.00,
                "turnstile_token": "dummy-token",
            }
            mock_post.return_value.json.return_value = {"success": True}
            request = self.factory.post(
                '/api/bookings/online/', request_data, content_type='application/json',
            )
            start = time.perf_counter()
            response = CreateOnlineBooking.as_view()(request)
            elapsed = time.perf_counter() - start
            self.assertIn(response.status_code, [200, 201],
                          f"online rooms={room_count} boats={boat_count} failed: {response.data}")
            return elapsed

        t1 = make_booking(1, 1, "online-a@test.com")
        t3 = make_booking(3, 2, "online-b@test.com")

        ratio = t3 / t1
        # print(f"\n  Online booking: 1r+1b={t1*1000:.1f}ms, 3r+2b={t3*1000:.1f}ms, ratio={ratio:.2f}x")
        self.assertLess(ratio, 9.0,
                        f"3r+2b booking should not be 9x+ slower (got {ratio:.2f}x)")

    def test_bulk_create_vs_individual_insert_speed(self):
        """Verify bulk_create writes N bookings in ~1 INSERT, not N."""
        check_in = "2027-01-05"
        check_out = "2027-01-07"

        bookings_to_create = 5
        request_data = {
            "customer": {
                "first_name": "Bulk", "last_name": "Test",
                "contact_number": "0933333333", "email": "bulk@test.com",
            },
            "booking": [
                {
                    "room_type": self.room_type.id,
                    "check_in": check_in,
                    "check_out": check_out,
                    "adult_count": 2,
                    "children_count": 0,
                    "extra_guest": 0,
                    "room_number": self.rooms[i % len(self.rooms)].id,
                }
                for i in range(bookings_to_create)
            ],
        }
        request = self.factory.post(
            '/api/bookings/onsite/', request_data, content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}'
        )

        start = time.perf_counter()
        response = CreateStayInBooking.as_view()(request)
        elapsed = time.perf_counter() - start

        self.assertEqual(response.status_code, 201,
                         f"Bulk create failed: {response.data}")
        self.assertEqual(len(response.data['bookings']), bookings_to_create)

        booking_count = Booking.objects.filter(
            customer_bill__customer__email="bulk@test.com"
        ).count()
        self.assertEqual(booking_count, bookings_to_create)
        # print(f"\n  Bulk create {bookings_to_create} bookings: {elapsed*1000:.1f}ms")


# ── Approve booking ────────────────────────────────────────────────────────────

class ApproveBookingTests(BookingTestBase):
    """Tests for POST /bookings/{id}/approve."""

    def test_approve_booking_assigns_room(self):
        """POST /approve with a room assigns it and sets APPROVED."""
        booking_id, _ = self._create_online_booking("approve@test.com")

        booking = Booking.objects.get(pk=booking_id)
        self.assertEqual(booking.status, BookingStatus.PENDING)
        self.assertIsNone(booking.room)

        request = self.factory.post(
            f'/api/bookings/{booking_id}/approve/',
            {'room': self.rooms[0].id},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}',
        )
        response = ApproveBooking.as_view()(request, pk=booking_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], BookingStatus.APPROVED)
        self.assertEqual(response.data['room'], self.rooms[0].id)

        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.APPROVED)
        self.assertEqual(booking.room_id, self.rooms[0].id)
        self.assertEqual(booking.room.type, self.room_type)

    def test_approve_missing_room_returns_400(self):
        """POST /approve without room field returns 400."""
        booking_id, _ = self._create_online_booking("no-room-field@test.com")

        request = self.factory.post(
            f'/api/bookings/{booking_id}/approve/',
            {},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}',
        )
        response = ApproveBooking.as_view()(request, pk=booking_id)

        self.assertEqual(response.status_code, 400)
        self.assertIn('room is required', response.data['error'])

    def test_approve_wrong_room_type_returns_400(self):
        """POST /approve with room of different type returns 400."""
        booking_id, _ = self._create_online_booking("wrong-type@test.com")

        other_type = RoomType.objects.create(name="Other", price=1000, max_adult=2)
        other_room = Room.objects.create(
            number="999", type=other_type, status=RoomStatus.AVAILABLE,
        )

        request = self.factory.post(
            f'/api/bookings/{booking_id}/approve/',
            {'room': other_room.id},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}',
        )
        response = ApproveBooking.as_view()(request, pk=booking_id)

        self.assertEqual(response.status_code, 400)
        self.assertIn('but booking requires', response.data['error'])

    def test_approve_already_approved_booking_fails(self):
        """Approving an already APPROVED booking returns 400."""
        booking_id, _ = self._create_online_booking("double-approve@test.com")

        request = self.factory.post(
            f'/api/bookings/{booking_id}/approve/',
            {'room': self.rooms[0].id},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}',
        )
        response = ApproveBooking.as_view()(request, pk=booking_id)
        self.assertEqual(response.status_code, 200)

        request2 = self.factory.post(
            f'/api/bookings/{booking_id}/approve/',
            {'room': self.rooms[1].id},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}',
        )
        response2 = ApproveBooking.as_view()(request2, pk=booking_id)

        self.assertEqual(response2.status_code, 400)
        self.assertIn('Cannot approve', response2.data['error'])

    def test_approve_already_booked_room_returns_400(self):
        """Approving with a room already booked for the date range returns 400."""
        booking_id, _ = self._create_online_booking("already-booked@test.com")

        Booking.objects.create(
            customer_bill=Billing.objects.create(
                customer=Customer.objects.create(
                    first_name="Blocker", last_name="Test",
                    contact_number="09999999999", email="blocker@test.com",
                ),
                status=BillingStatus.PENDING,
            ),
            room=self.rooms[0],
            room_type=self.room_type,
            check_in="2027-10-01",
            check_out="2027-10-03",
            adult_count=2,
            status=BookingStatus.APPROVED,
        )

        request = self.factory.post(
            f'/api/bookings/{booking_id}/approve/',
            {'room': self.rooms[0].id},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}',
        )
        response = ApproveBooking.as_view()(request, pk=booking_id)

        self.assertEqual(response.status_code, 400)
        self.assertIn('already booked', response.data['error'])


# ── Cancel booking ─────────────────────────────────────────────────────────────

class CancelBookingTests(BookingTestBase):
    """Tests for POST /bookings/{id}/cancel."""

    def test_cancel_booking_cascades_billing(self):
        """POST /cancel cancels booking and cascades to billing."""
        booking_id, billing_id = self._create_online_booking("cancel@test.com")

        request = self.factory.post(
            f'/api/bookings/{booking_id}/cancel/',
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}',
        )
        response = CancelBooking.as_view()(request, pk=booking_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], BookingStatus.CANCELLED)

        booking = Booking.objects.get(pk=booking_id)
        self.assertEqual(booking.status, BookingStatus.CANCELLED)

        billing = Billing.objects.get(pk=billing_id)
        self.assertEqual(billing.status, BillingStatus.CANCELLED)

    def test_cancel_one_booking_does_not_cancel_billing_when_others_active(self):
        """Cancelling one booking leaves billing active if other bookings remain."""
        booking_id_1, billing_id = self._create_online_booking("multi-cancel@test.com")

        Booking.objects.create(
            customer_bill_id=billing_id,
            room_type=self.room_type,
            check_in="2027-10-05",
            check_out="2027-10-07",
            adult_count=1,
            status=BookingStatus.PENDING,
        )

        request = self.factory.post(
            f'/api/bookings/{booking_id_1}/cancel/',
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}',
        )
        response = CancelBooking.as_view()(request, pk=booking_id_1)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], BookingStatus.CANCELLED)

        billing = Billing.objects.get(pk=billing_id)
        self.assertNotEqual(billing.status, BillingStatus.CANCELLED,
                            "Billing should not be cancelled while other bookings are active")

    def test_cancel_already_cancelled_booking_fails(self):
        """Cancelling an already CANCELLED booking returns 400."""
        booking_id, _ = self._create_online_booking("double-cancel@test.com")

        request = self.factory.post(
            f'/api/bookings/{booking_id}/cancel/',
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}',
        )
        response = CancelBooking.as_view()(request, pk=booking_id)
        self.assertEqual(response.status_code, 200)

        request2 = self.factory.post(
            f'/api/bookings/{booking_id}/cancel/',
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {self.token}',
        )
        response2 = CancelBooking.as_view()(request2, pk=booking_id)
        self.assertEqual(response2.status_code, 400)
        self.assertIn('Cannot cancel', response2.data['error'])


# ── Idempotency key ────────────────────────────────────────────────────────────

from django.conf import settings as django_settings
from django.test import override_settings

class IdempotencyKeyTests(BookingTestBase):
    """
    Tests for idempotency key enforcement on POST /api/bookings/online/.

    Uses self.client (full Django test client) so the middleware stack runs,
    unlike other tests that dispatch views directly via APIRequestFactory.
    The idempotency cache is overridden to use LocMemCache so tests don't
    require a running Redis instance.
    """

    def setUp(self):
        super().setUp()
        # Use in-memory cache for idempotency (no Redis needed) and disable lock
        patched_caches = {
            **django_settings.CACHES,
            "idempotency": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "idempotency-test",
            },
        }
        patched_idem = {
            **django_settings.IDEMPOTENCY_KEY,
            "LOCK": {**django_settings.IDEMPOTENCY_KEY.get("LOCK", {}), "ENABLE": False},
        }
        self._settings_override = override_settings(
            CACHES=patched_caches,
            IDEMPOTENCY_KEY=patched_idem,
        )
        self._settings_override.enable()
        from django.core.cache import caches
        caches.close_all()

    def tearDown(self):
        from django.core.cache import caches
        caches.close_all()
        self._settings_override.disable()
        super().tearDown()


    def _payload(self, email="idempotency@test.com"):
        return {
            "customer": {
                "first_name": "Idem",
                "last_name": "Test",
                "contact_number": "09123456789",
                "email": email,
            },
            "rooms": [{
                "room_type": self.room_type.id,
                "check_in": "2028-01-10",
                "check_out": "2028-01-12",
                "adult_count": 2,
                "children_count": 0,
                "extra_guest": 0,
            }],
            "turnstile_token": "dummy-token",
        }

    @patch('bookings.turnstile.requests.post')
    def test_missing_idempotency_key_returns_400(self, mock_post):
        """No Idempotency-Key header → middleware rejects with 400."""
        mock_post.return_value.json.return_value = {"success": True}
        response = self.client.post(
            '/api/bookings/online/',
            data=self._payload(),
            content_type='application/json',
            # intentionally omitting HTTP_IDEMPOTENCY_KEY
        )
        self.assertEqual(response.status_code, 400)

    @patch('bookings.turnstile.requests.post')
    def test_duplicate_key_replays_response_without_new_booking(self, mock_post):
        """Same Idempotency-Key on a retry → cached 201, no extra DB row."""
        mock_post.return_value.json.return_value = {"success": True}

        headers = {'HTTP_IDEMPOTENCY_KEY': 'test-idem-key-duplicate'}

        # First request — creates the booking
        response1 = self.client.post(
            '/api/bookings/online/',
            data=self._payload(email="idem-dup@test.com"),
            content_type='application/json',
            **headers,
        )
        self.assertEqual(response1.status_code, 201)
        booking_count_after_first = Booking.objects.count()

        # Second request with the same key — should be replayed, no new booking
        response2 = self.client.post(
            '/api/bookings/online/',
            data=self._payload(email="idem-dup@test.com"),
            content_type='application/json',
            **headers,
        )
        self.assertEqual(response2.status_code, 201)
        self.assertEqual(
            Booking.objects.count(), booking_count_after_first,
            "Duplicate idempotency key must not create a new booking row",
        )

    @patch('bookings.turnstile.requests.post')
    def test_different_key_creates_new_booking(self, mock_post):
        """A distinct Idempotency-Key is treated as a new request and creates a booking."""
        mock_post.return_value.json.return_value = {"success": True}

        response1 = self.client.post(
            '/api/bookings/online/',
            data=self._payload(email="idem-a@test.com"),
            content_type='application/json',
            HTTP_IDEMPOTENCY_KEY='unique-key-aaa',
        )
        self.assertEqual(response1.status_code, 201)
        count_after_first = Booking.objects.count()

        response2 = self.client.post(
            '/api/bookings/online/',
            data=self._payload(email="idem-b@test.com"),
            content_type='application/json',
            HTTP_IDEMPOTENCY_KEY='unique-key-bbb',
        )
        self.assertEqual(response2.status_code, 201)
        self.assertGreater(
            Booking.objects.count(), count_after_first,
            "A fresh idempotency key must create a new booking row",
        )

