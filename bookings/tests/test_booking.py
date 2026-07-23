from django.test import TestCase, RequestFactory

from bookings.models import Booking, Room, RoomType, BookingStatus, RoomStatus
from bookings.views.bookings import CreateOnlineBooking, CreateStayInBooking
from transactions.models import Billing, Customer, Amenities, AmenitiesAvailed, GuestList


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
        self.room= Room.objects.create(
            number="101",
            type=self.room_type,
            status=RoomStatus.AVAILABLE,
        )
        # Shared Amenities
        self.amenities = Amenities.objects.create(
            amenity="Boat Transfer",
            rate_per_head=500.00,
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
                "room_number": self.room.id
            }],
        }

        request = self.factory.post(
            '/api/bookings/stay-in/', request_data, content_type='application/json',
        )
        response = CreateStayInBooking.as_view()(request)

        # Update assertions based on your endpoint's expected response
        self.assertIn(response.status_code, [200, 201])

    def tearDown(self):
        # Delete dependent child objects first (respecting PROTECT FKs)
        Booking.objects.all().delete()
        AmenitiesAvailed.objects.all().delete()
        GuestList.objects.all().delete()
        Billing.objects.all().delete()
        
        # Delete parent objects after children are cleared
        Customer.objects.all().delete()
        Amenities.objects.all().delete()
        Room.objects.all().delete()
        RoomType.objects.all().delete()