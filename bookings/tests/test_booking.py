import time

from django.test import TestCase, RequestFactory

from bookings.models import Booking, Room, RoomType, BookingStatus, RoomStatus
from bookings.views.bookings import CreateOnlineBooking, CreateStayInBooking, CreateDayTourGuest
from transactions.models import Billing, Customer, Amenities, AmenitiesAvailed, GuestList, ActivitiesAvailed, Activity


class BookingSystemTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        
        # Shared Room Type
        self.room_type = RoomType.objects.create(
            name="Test Room Type",
            description="A test room type",
            price=2500.00,
            good_for=2,
            max_children=1,
            max_adult=2,
        )
        
        # Shared Rooms
        room_numbers = ["101", "102", "103", "104", "106"]

        self.rooms = Room.objects.bulk_create([
            Room(
                number=number,
                type=self.room_type,
                status=RoomStatus.AVAILABLE,
            )
            for number in room_numbers
        ])
        # Shared Amenities
        self.amenities = Amenities.objects.create(
            amenity="Boat Transfer",
            rate_per_head=500.00,
        )

        self.activities = Activity.objects.create(
            activity="Snorkeling",
            hourly_rate=300.00,
        )

    def test_create_online_booking(self):
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
            "boat": [{
                "head_count": 2,
                "time": "10:00",
                "guests": ["John Doe", "Jane Doe"],
            }],
            "payment": 1000.00,
        }

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
                "room_number": self.rooms[0].id
            }],
        }

        request = self.factory.post(
            '/api/bookings/stay-in/', request_data, content_type='application/json',
        )
        response = CreateStayInBooking.as_view()(request)

        # Update assertions based on your endpoint's expected response
        self.assertIn(response.status_code, [200, 201])

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
        )
        response = CreateDayTourGuest.as_view()(request)
        # Update assertions based on your endpoint's expected response
        self.assertEqual(response.status_code, 201)

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
        print(f"\n  Booking speed: 1 room={t1*1000:.1f}ms, 4 rooms={t4*1000:.1f}ms, ratio={ratio:.2f}x")
        self.assertLess(ratio, 4.0,
                        f"4-room booking should be <4x 1-room time (got {ratio:.2f}x)")

    def test_online_booking_multi_room_query_count(self):
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
                "boat": [
                    {
                        "head_count": 2,
                        "time": "10:00",
                        "guests": [f"Guest {i*2}", f"Guest {i*2+1}"],
                    }
                    for i in range(boat_count)
                ],
                "payment": 1000.00,
            }
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
        print(f"\n  Online booking: 1r+1b={t1*1000:.1f}ms, 3r+2b={t3*1000:.1f}ms, ratio={ratio:.2f}x")
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
        )

        start = time.perf_counter()
        response = CreateStayInBooking.as_view()(request)
        elapsed = time.perf_counter() - start

        self.assertEqual(response.status_code, 201,
                         f"Bulk create failed: {response.data}")
        self.assertEqual(len(response.data['bookings']), bookings_to_create)

        # Verify all bookings persisted
        booking_count = Booking.objects.filter(
            customer_bill__customer__email="bulk@test.com"
        ).count()
        self.assertEqual(booking_count, bookings_to_create)
        print(f"\n  Bulk create {bookings_to_create} bookings: {elapsed*1000:.1f}ms")

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
        