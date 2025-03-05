from django.core.management.base import BaseCommand

from transactions.models import Activity, Amenities, PaymentStatus, PaymentMethod, PaymentFor, GuestStatus, BillingStatus


class Command(BaseCommand):
    help = "Populates the database with sample data for development purposes."

    def handle(self, *args, **kwargs):    

        payment_status_data = ['Full', 'Partial', 'Down Payment']

        for status in payment_status_data:  
            PaymentStatus.objects.get_or_create(status=status)

        payment_method_data = ['cash', 'gcash', 'card']
        for method in payment_method_data:
            PaymentMethod.objects.get_or_create(mode=method)

        payment_for_data = ['Down payment', 'Room', 'Food', 'Amenities', 'Activities']

        for item in payment_for_data:
            PaymentFor.objects.get_or_create(name=item)

        guest_status_data = ['Not Arrived', 'In Port', 'In Boat', 'In Resort', 'In Boat (Leaving)', 'Checked Out']

        for status in guest_status_data:
            GuestStatus.objects.get_or_create(status=status)
        
        billing_status_data = ['Processing', 'Complete', 'Pending', 'Confirmed', 'Cancelled']

        for status in billing_status_data:
            billing_status, created = BillingStatus.objects.get_or_create(status=status)
            if created:
                print(f"Created billing status: {status}")
            else:
                print(f"Billing status already exists: {status}")


        activity_base_data = [
            {"activity": "Kayak", "hourly_rate": 200},
            {"activity": "Jetski", "hourly_rate": 3000},
            {"activity": "Delta", "hourly_rate": 1500},
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
            {"amenity": "Pillow", "rate_per_head": 50},
            {"amenity": "Blanket", "rate_per_head": 100},
            {"amenity": "Towel", "rate_per_head": 50}, 
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





