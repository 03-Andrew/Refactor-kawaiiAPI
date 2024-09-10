from datetime import datetime, timedelta
from django.shortcuts import render
from django.db.models import Count, Q
from .models import Room, Booking
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view
from .serializers import AvailableRoomSerializer
from datetime import datetime, timedelta

def home(request):
    return HttpResponse("Hello, World!")


def get_checkin_checkout_dates(request):
    """Retrieve or set default check-in and check-out dates."""
    checkin_str = request.session.get('checkin')
    checkout_str = request.session.get('checkout')

    if checkin_str and checkout_str:
        checkin = datetime.strptime(checkin_str, '%Y-%m-%d').date()
        checkout = datetime.strptime(checkout_str, '%Y-%m-%d').date()
    else:
        today = datetime.now().date()
        checkin = today
        checkout = today + timedelta(days=1)
        request.session['checkin'] = checkin.strftime('%Y-%m-%d')
        request.session['checkout'] = checkout.strftime('%Y-%m-%d')

    return checkin, checkout

def get_total_room_counts():
    """Get the total count of rooms by type."""
    return Room.objects.values(
        'type__id', 'type__name', 'type__price', 'type__description',
        'type__good_for', 'type__max_children', 'type__max_adult'
    ).annotate(total_count=Count('id')).order_by('type__name')

def get_booked_room_counts(checkin, checkout):
    """Get the count of booked rooms by type within a date range."""
    return Booking.objects.filter(
        Q(check_in__lt=checkout) & Q(check_out__gt=checkin)
    ).values(
        'room_type__id', 'room_type__name', 'room_type__price', 'room_type__description',
        'room_type__good_for', 'room_type__max_children', 'room_type__max_adult'
    ).annotate(booked_count=Count('id'))

def create_booked_rooms_dict(booked_rooms):
    """Convert booked rooms into a dictionary for easy lookup."""
    return {
        (room['room_type__name'], room['room_type__price']): room['booked_count']
        for room in booked_rooms
    }

def calculate_available_rooms(room_counts, booked_rooms_dict):
    """Calculate available rooms based on total and booked counts."""
    available_rooms = {}
    for room in room_counts:
        room_type_name = room['type__name']
        room_type_price = room['type__price']
        total_count = room['total_count']

        booked_count = booked_rooms_dict.get(
            (room_type_name, room_type_price), 0
        )  # Default to 0 if not booked

        available_count = total_count - booked_count
        available_rooms[room_type_name] = {
            'id': room['type__id'],
            'price': room_type_price,
            'description': room['type__description'],
            'good_for': room['type__good_for'],
            'max_children': room['type__max_children'],
            'max_adult': room['type__max_adult'],
            'count': available_count
        }
    return available_rooms

def available_rooms(request):
    """Retrieve available rooms based on check-in and check-out dates."""
    # Step 1: Get check-in and check-out dates
    checkin, checkout = get_checkin_checkout_dates(request)
    checkin_str = checkin.strftime('%Y-%m-%d')
    checkout_str = checkout.strftime('%Y-%m-%d')

    # Step 2: Get room counts and booked room counts
    room_counts = get_total_room_counts()
    booked_rooms = get_booked_room_counts(checkin, checkout)

    # Step 3: Calculate available rooms
    booked_rooms_dict = create_booked_rooms_dict(booked_rooms)
    available_rooms = calculate_available_rooms(room_counts, booked_rooms_dict)

    # Step 4: Prepare context and render template
    context = {
        'available_rooms': available_rooms,
        'pre_booking_data': {
            'checkin': checkin_str,
            'checkout': checkout_str,
            'adults': 2,
            'children': 0
        }
    }

    return render(request, 'base/booking_page.html', context)



@api_view(['GET'])
def available_rooms_api(request):
    """API to retrieve available rooms based on check-in and check-out dates."""
    # Step 1: Get check-in and check-out dates
    checkin, checkout = get_checkin_checkout_dates(request)
    
    # Step 2: Get room counts and booked room counts
    room_counts = get_total_room_counts()
    booked_rooms = get_booked_room_counts(checkin, checkout)

    # Step 3: Calculate available rooms
    booked_rooms_dict = create_booked_rooms_dict(booked_rooms)
    available_rooms = calculate_available_rooms(room_counts, booked_rooms_dict)

    # Serialize available rooms data
    serialized_rooms = [AvailableRoomSerializer(room).data for room in available_rooms.values()]

    # Step 4: Prepare the response data
    response_data = {
        'available_rooms': serialized_rooms,
    }

    return Response(response_data)