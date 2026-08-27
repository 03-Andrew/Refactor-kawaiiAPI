
from .models import Billing, BillingStatus, GuestList, GuestStatus, AmenitiesAvailed, Amenities, ActivitiesAvailed


def create_billing(*, customer, billing_status=None):
    return Billing.objects.create(
        customer=customer,
        status=billing_status or BillingStatus.PENDING,
    )

def create_amenity_availed(*, billing, amenity, head_count, time):
    amenity_item = Amenities.objects.get(amenity=amenity)
    return AmenitiesAvailed.objects.create(
        customer_bill=billing,
        amenity=amenity_item,
        head_count = head_count,
        time = time
    )

def create_amenities_availed_bulk(*, billing, amenities):
    amenities_availed = [
        AmenitiesAvailed(
            customer_bill = billing,
            amenity_id=amenity['id'],
            head_count=amenity['head_count'],
        )
        for amenity in amenities
    ]
    return AmenitiesAvailed.objects.bulk_create(amenities_availed)

def create_activities_availed_bulk(*, billing, activities):
    activities_availed = [
        ActivitiesAvailed(
            customer_bill = billing,
            activity_id = activity['id'],
            hours_availed= activity['hours']
        )
        for activity in activities
    ]
    return ActivitiesAvailed.objects.bulk_create(activities_availed)

def create_guest_list(*, billing, guests, status=GuestStatus.PENDING):
    guest_list = [
        GuestList(
            customer_bill=billing,
            guest=guest,
            status=status
        )
        for guest in guests
    ]
    return GuestList.objects.bulk_create(guest_list)


