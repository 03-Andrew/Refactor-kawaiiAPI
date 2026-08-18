from django.core.management.base import BaseCommand
from bookings.models import Inclusions, RoomType, Room
from transactions.models import Amenities, PaymentMethod, PaymentStatus


class Command(BaseCommand):
    help = 'Seed database with inclusions, room types, rooms, amenities, and payment methods'

    def handle(self, *args, **options):
        self._seed_inclusions()
        self._seed_room_types()
        self._seed_rooms()
        self._seed_amenities()
        self._seed_payment_methods()
        self._seed_payment_statuses()
        self.stdout.write(self.style.SUCCESS('Done.'))

    def _seed_inclusions(self):
        items = [
            'Air Conditioning',
            'Flat Screen TV',
            'Mini Bar',
            'Coffee Maker',
            'Free WiFi',
            'Hot & Cold Shower',
            'Toiletries Kit',
            'Towels',
            'Slippers',
            'Hair Dryer',
            'Room Service',
            'Breakfast Buffet',
            'Beach Access',
            'Pool Access',
            'Parking',
        ]
        created = 0
        for name in items:
            _, new = Inclusions.objects.get_or_create(inclusion=name)
            if new:
                created += 1
        self.stdout.write(f'Inclusions: {created} created, {len(items) - created} already exist')

    def _seed_room_types(self):
        types = [
            {
                'name': 'Standard Room',
                'price': 2500.00,
                'description': 'Cozy room with basic amenities. Garden view.',
                'good_for': 2,
                'max_children': 1,
                'max_adult': 2,
                'inclusions': ['Air Conditioning', 'Free WiFi', 'Hot & Cold Shower', 'Towels', 'Toiletries Kit'],
            },
            {
                'name': 'Deluxe Room',
                'price': 4500.00,
                'description': 'Spacious room with premium amenities. Pool view.',
                'good_for': 4,
                'max_children': 2,
                'max_adult': 2,
                'inclusions': ['Air Conditioning', 'Flat Screen TV', 'Free WiFi', 'Hot & Cold Shower', 'Towels', 'Toiletries Kit', 'Slippers', 'Mini Bar', 'Pool Access'],
            },
            {
                'name': 'Family Room',
                'price': 6000.00,
                'description': 'Large room for families. Two queen beds. Garden view.',
                'good_for': 6,
                'max_children': 3,
                'max_adult': 3,
                'inclusions': ['Air Conditioning', 'Flat Screen TV', 'Free WiFi', 'Hot & Cold Shower', 'Towels', 'Toiletries Kit', 'Slippers', 'Coffee Maker', 'Breakfast Buffet', 'Pool Access'],
            },
        ]

        for rt in types:
            inclusions = rt.pop('inclusions')
            obj, created = RoomType.objects.get_or_create(name=rt['name'], defaults=rt)
            if created:
                obj.inclusions.set(Inclusions.objects.filter(inclusion__in=inclusions))
                self.stdout.write(f'RoomType: {obj.name} created')
            else:
                self.stdout.write(f'RoomType: {obj.name} already exists')

    def _seed_rooms(self):
        layout = {
            'Standard Room': list(range(101, 111)),      # 10 rooms
            'Deluxe Room': list(range(201, 209)),         # 8 rooms
            'Family Room': list(range(301, 306)),         # 5 rooms
            
        }
        created = 0
        for type_name, numbers in layout.items():
            room_type = RoomType.objects.get(name=type_name)
            for num in numbers:
                _, new = Room.objects.get_or_create(
                    number=str(num),
                    defaults={'type': room_type},
                )
                if new:
                    created += 1
        self.stdout.write(f'Rooms: {created} created')

    def _seed_amenities(self):
        amenities = [
            {'id': 1, 'amenity': 'Boat Transfer', 'rate_per_head': 500.00},
        ]
        created = 0
        for item in amenities:
            amenity_id = item.pop('id')
            _, new = Amenities.objects.get_or_create(id=amenity_id, defaults=item)
            if new:
                created += 1
        self.stdout.write(f'Amenities: {created} created')

    def _seed_payment_methods(self):
        methods = ['gcash', 'card', 'qrph', 'paymaya', 'cash']
        created = 0
        for mode in methods:
            _, new = PaymentMethod.objects.get_or_create(mode=mode)
            if new:
                created += 1
        self.stdout.write(f'Payment Methods: {created} created')

    def _seed_payment_statuses(self):
        statuses = ['Paid', 'Pending', 'Failed']
        created = 0
        for status_name in statuses:
            _, new = PaymentStatus.objects.get_or_create(status=status_name)
            if new:
                created += 1
        self.stdout.write(f'Payment Statuses: {created} created')

