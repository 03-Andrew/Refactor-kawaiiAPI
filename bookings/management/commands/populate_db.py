from django.core.management.base import BaseCommand
from bookings.models import Inclusions, RoomStatus, RoomType, Room, BookingStatus
from transactions.models import Activity, Amenities


class Command(BaseCommand):
    help = "Populates the database with sample data for development purposes."

    def handle(self, *args, **kwargs):       
        activity_base_data = [
            {"activity": "Kayak", "hourly_rate": 200},
            {"activity": "Jetski", "hourly_rate": 200},
            {"activity": "Delta", "hourly_rate": 200},
            {"activity": "Darts", "hourly_rate": 200},
            {"activity": "Billiards", "hourly_rate": 200}, 
        ]

        for activity_data in activity_base_data:
            activity, created = Activity.objects.get_or_create(
                activity=activity_data["activity"],
                defaults={"hourly_rate": activity_data["hourly_rate"]}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created activity: {activity.activity}"))
            else:
                self.stdout.write(f"Activity already exists: {activity.activity}")

        amenity_base_data = [
            {"amenity": "Boat Transfer", "rate_per_head": 200},
            {"amenity": "Day Tour", "rate_per_head": 200},
            {"amenity": "Vanishing Island", "rate_per_head": 200},
            {"amenity": "Party Boat", "rate_per_head": 200},
            {"amenity": "Pillow", "rate_per_head": 200},
            {"amenity": "Blanket", "rate_per_head": 200},
            {"amenity": "Towel", "rate_per_head": 200}, 
            {"amenity": "Comforter", "rate_per_head": 200},
        ]

        for amenity_data in amenity_base_data:
            amenity, created = Amenities.objects.get_or_create(
                amenity=amenity_data["amenity"],
                defaults={"rate_per_head": amenity_data["rate_per_head"]}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created activity: {amenity.amenity}"))
            else:
                self.stdout.write(f"Activity already exists: {activity.activity}")
                
        self.stdout.write(self.style.SUCCESS("Database populated successfully!"))

