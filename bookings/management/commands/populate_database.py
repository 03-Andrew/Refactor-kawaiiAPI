from django.core.management.base import BaseCommand
from bookings.models import Inclusions, RoomStatus, RoomType, Room, BookingStatus

class Command(BaseCommand):
    help = "Populates the database with sample data for development purposes."

    def handle(self, *args, **kwargs):
        # Step 1: Add inclusions
        inclusions_data = ["Free WiFi", "Air Conditioning", "TV", "Breakfast Included"]
        inclusion_objects = [Inclusions.objects.get_or_create(inclusion=incl)[0] for incl in inclusions_data]

        booking_status = ["pending", "approved"]
        for status in booking_status:
            BookingStatus.objects.get_or_create(name=status)

        # Step 2: Add room statuses
        statuses_data = ["available", "under maintenance"]
        status_objects = [RoomStatus.objects.get_or_create(name=status)[0] for status in statuses_data]

        # Step 3: Add room types
        room_types_data = [
            {
                "name": "Deluxe",
                "price": 4500.00,
                "description": "A cozy room for two people.",
                "good_for": 2,
                "max_children": 2,
                "max_adult": 2,
                "inclusions": ["Free WiFi", "TV", "Breakfast Included"]
            },
            {
                "name": "Superior",
                "price": 4500,
                "description": "A comfortable room for two people.",
                "good_for": 2,
                "max_children": 1,
                "max_adult": 2,
                "inclusions": ["Free WiFi", "TV", "Breakfast Included"]
            },
            {
                "name": "Suite",
                "price": 150.00,
                "description": "A luxurious suite for the whole family.",
                "good_for": 4,
                "max_children": 2,
                "max_adult": 3,
                "inclusions": ["Free WiFi", "Air Conditioning", "TV", "Breakfast Included"]
            },
        ]
        room_type_objects = []
        for room_type in room_types_data:
            rt, created = RoomType.objects.get_or_create(
                name=room_type["name"],
                price=room_type["price"],
                description=room_type["description"],
                good_for=room_type["good_for"],
                max_children=room_type["max_children"],
                max_adult=room_type["max_adult"],
            )
            rt.inclusions.set(Inclusions.objects.filter(inclusion__in=room_type["inclusions"]))
            room_type_objects.append(rt)

        # Step 4: Add rooms
        rooms_data = [
            {"number": 1, "type": "Superior", "status": "available"},
            {"number": 2, "type": "Superior", "status": "available"},
            {"number": 3, "type": "Superior", "status": "available"},
            {"number": 4, "type": "Superior", "status": "available"},
            {"number": 5, "type": "Superior", "status": "available"},
            {"number": 6, "type": "Superior", "status": "available"},
            {"number": 7, "type": "Deluxe", "status": "available"},
            {"number": 8, "type": "Superior", "status": "available"},
            {"number": 9, "type": "Deluxe", "status": "available"},
            {"number": 10, "type": "Deluxe", "status": "available"},
            {"number": 11, "type": "Superior", "status": "available"},
            {"number": 12, "type": "Superior", "status": "available"},
            {"number": 13, "type": "Deluxe", "status": "available"},
            {"number": 14, "type": "Deluxe", "status": "under maintenance"},
            {"number": 15, "type": "Suite", "status": "available"},
        ]
        for room in rooms_data:
            Room.objects.get_or_create(
                number=room["number"],
                type=RoomType.objects.get(name=room["type"]),
                status=RoomStatus.objects.get(name=room["status"]),
            )

        self.stdout.write(self.style.SUCCESS("Database populated successfully!"))
