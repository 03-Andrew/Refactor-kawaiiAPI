import os
import django
from contextlib import contextmanager
from django.test.utils import setup_test_environment, teardown_test_environment
from django.test.runner import DiscoverRunner
from decimal import Decimal

from unittest.mock import patch
import uuid

@contextmanager
def temporary_test_database():
    """
    Spins up an isolated ephemeral test database, runs all migrations,
    seeds test inventory, mocks Redis locking with unittest.mock, and tears down on exit.
    """
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kawaiiAPI.settings.dev')
    django.setup()
    
    setup_test_environment()
    runner = DiscoverRunner(verbosity=0, interactive=False)
    
    # 1. Creates test database and executes migrations
    old_config = runner.setup_databases()
    print("Ephemeral test database created and migrated.")

    try:
        # 2. Mock Redis lock functions so tests run without requiring a Redis server
        with patch("bookings.services.lock.bulk_acquire", side_effect=lambda reqs, ttl=600: (True, str(uuid.uuid4()), [])), \
             patch("bookings.services.lock.acquire_room_type_lock", side_effect=lambda *args, **kwargs: (True, kwargs.get("holder_id") or str(uuid.uuid4()))), \
             patch("bookings.services.lock.release_holder_locks", return_value=True), \
             patch("bookings.services.lock.release_room_type_lock", return_value=True), \
             patch("bookings.services.lock.get_locked_count", return_value=0), \
             patch("bookings.services.lock.holder_has_lock", return_value=True):
            
            seed_test_inventory()
            yield
    finally:
        # 3. Destroys the test database completely
        runner.teardown_databases(old_config)
        teardown_test_environment()
        print("Ephemeral test database deleted.")

def seed_test_inventory():
    """Seed room types and physical room units for availability checks."""
    from bookings.models import RoomType, Room, RoomStatus
    
    # 1. Room Types matching resort policy specifications
    rt_standard = RoomType.objects.create(
        id=1,
        name="Standard Room",
        price=Decimal("2500.00"),
        good_for=2,
        max_extra_guest=1,
        description="Cozy room with queen bed"
    )
    rt_deluxe = RoomType.objects.create(
        id=2,
        name="Deluxe Room",
        price=Decimal("4500.00"),
        good_for=4,
        max_extra_guest=1,
        description="Pool view with balcony and two double beds"
    )
    rt_family = RoomType.objects.create(
        id=3,
        name="Family Room",
        price=Decimal("6000.00"),
        good_for=6,
        max_extra_guest=2,
        description="Large room with two queen beds and breakfast included"
    )
    
    # 2. Physical Room Units (so Count('room') returns available units)
    rooms = []
    for i in range(1, 11):
        rooms.append(Room(number=f"10{i}" if i < 10 else f"1{i}", type=rt_standard, status=RoomStatus.AVAILABLE))
    for i in range(1, 9):
        rooms.append(Room(number=f"20{i}", type=rt_deluxe, status=RoomStatus.AVAILABLE))
    for i in range(1, 6):
        rooms.append(Room(number=f"30{i}", type=rt_family, status=RoomStatus.AVAILABLE))

    Room.objects.bulk_create(rooms)
    
    # 3. Seed Boat Transfer amenity for online bookings
    from transactions.models import Amenities
    Amenities.objects.create(
        amenity="Boat Transfer",
        rate_per_head=Decimal("200.00")
    )

    print("Seeded 3 Room Types, 23 Rooms, and Boat Transfer amenity into test DB.")
