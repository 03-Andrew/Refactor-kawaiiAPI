from datetime import datetime, timedelta
from django.shortcuts import render
from django.db.models import Count, Q
from django.http import HttpResponse

from .models import Room, Booking, RoomType
from .serializers import AvailableRoomSerializer, BookingSerializer, RoomSerializer, AvailableRoomSerializer2, RoomTypeSerializer, CurrentRoomBookings

from transactions.serializers import CustomerSerializer, BillingSerialzerBase

from rest_framework.views import APIView
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework.pagination import LimitOffsetPagination

from django.db import transaction
from datetime import datetime, timedelta, date


def home(request):
    return render(request, 'base/home.html')


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


# API
@api_view(['GET'])
def get_available_rooms1(request):
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

class AvailableRoomsView(generics.ListAPIView):
    serializer_class = AvailableRoomSerializer2

    def get_queryset(self):
        check_in = self.request.query_params.get('check_in')
        check_out = self.request.query_params.get('check_out')
        room_type_id = self.request.query_params.get('room_type')  # Filter by room type

        if not check_in or not check_out:
            return Room.objects.none()  # Return an empty queryset if dates are not provided

        # Convert string dates to date objects
        try:
            check_in_date = date.fromisoformat(check_in)
            check_out_date = date.fromisoformat(check_out)
        except ValueError:
            return Room.objects.none()  # Return an empty queryset on date parsing error

        # Condition to find rooms that overlap with the selected dates
        booked_rooms_condition = Q(booking__check_in__lt=check_out_date) & Q(booking__check_out__gt=check_in_date)

        # Get available rooms that are not booked in the given date range and have status = 1 (available)
        available_rooms = Room.objects.filter(status=1).exclude(
            id__in=Booking.objects.filter(booked_rooms_condition).values_list('room_id', flat=True)
        )

        # If room_type_id is provided, filter rooms by the selected room type
        if room_type_id:
            available_rooms = available_rooms.filter(type_id=room_type_id)

        return available_rooms
    


class AvailableRooms(generics.ListAPIView):
    serializer_class = AvailableRoomSerializer2
    
    def get_queryset(self):
        check_in = self.request.GET.get('check_in')
        check_out = self.request.GET.get('check_out')
        r_type = self.request.GET.get('type')
        
        if not r_type:
            r_type = 1

        # Set default dates if not provided
        if not check_in or not check_out:
            today = datetime.today().date()
            check_in_date = today
            check_out_date = today + timedelta(days=1)
        else:
            try:
                check_in_date = datetime.strptime(check_in, "%Y-%m-%d").date()
                check_out_date = datetime.strptime(check_out, "%Y-%m-%d").date()
            except ValueError:
                raise ValueError("Invalid date format. Use YYYY-MM-DD.")

        # Ensure that check-in is before check-out
        if check_in_date >= check_out_date:
            raise ValueError("Check-in date must be before check-out date.")

        # Return available rooms
        queryset = Room.objects.exclude(
            Q(bookings__check_in__lt=check_out_date) & Q(bookings__check_out__gt=check_in_date)
        ).distinct().filter(status__id=1).filter(type__id=r_type)
        

        return queryset

    def get(self, request):
        try:
            available_rooms = self.get_queryset()
            # Serialize the available rooms
            serializer = self.get_serializer(available_rooms, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class BookingListCreate(generics.ListCreateAPIView):
    serializer_class = BookingSerializer
    def get_queryset(self):
        queryset = Booking.objects.all()
        s = self.request.GET.get('s')
        sort = self.request.GET.get('sort')
        status_filter = self.request.GET.get('status')
        
        if s:
            queryset = queryset.filter(
                Q(billing__customer__first_name__icontains=s) | 
                Q(billing__customer__last_name__icontains=s)
            )
        
        if status_filter:
            if status_filter == 'a': 
                queryset = queryset.filter(status__exact=2)
            elif status_filter == 'p':
                queryset = queryset.filter(status__exact=1)
        
        if sort == "asc":
            queryset = queryset.order_by('check_in')
        elif sort == "desc":
            queryset = queryset.order_by('-check_in')
        return queryset
    


class RoomListCreateView(generics.ListAPIView):
    serializer_class = RoomSerializer
 
    def get_queryset(self):
        queryset = Room.objects.all()
        room_type = self.request.GET.get('type')  # Filter by type name
        sort_order = self.request.GET.get('sort')  # Sort rooms by ID

        # Filter by room type name if provided
        if room_type:
            queryset = queryset.filter(
                type__name__icontains=room_type
            )

        # Sort rooms by ID if the sort order is provided
        if sort_order == "asc":
            queryset = queryset.order_by('id')
        elif sort_order == "desc":
            queryset = queryset.order_by('-id')

        return queryset

    def perform_create(self, serializer):
        serializer.save()


class RoomDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Room.objects.all()
    serializer_class = RoomSerializer


class CreateStayInBooking(APIView):
    def post(self, request):
        customer_data = request.data.get('customer')
        billing_data = request.data.get('billing')
        booking_data = request.data.get('booking')

        # Using a transaction to ensure atomicity
        with transaction.atomic():
            # Handle customer creation
            customer_serializer = CustomerSerializer(data=customer_data)
            if customer_serializer.is_valid():
                customer = customer_serializer.save()
            else:
                return Response(customer_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            # Handle billing creation
            billing_data['customer'] = customer.id
            billing_serializer = BillingSerialzerBase(data=billing_data)
            if billing_serializer.is_valid():
                billing = billing_serializer.save()
            else:
                return Response(billing_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            # Create bookings Hue
            created_bookings = []
            for rBooking in booking_data:
                self._prepare_booking_data(rBooking, billing.id)
                booking_serializer = BookingSerializer(data=rBooking)
                
                if booking_serializer.is_valid():
                    booking = booking_serializer.save()
                    created_bookings.append(booking_serializer.data)
                else:
                    # If booking serializer is invalid, raise an exception to rollback
                    raise Exception(booking_serializer.errors)

        # Return the response after all bookings are processed
        return Response({
            'customer': customer_serializer.data,
            'billing': billing_serializer.data,
            'bookings': created_bookings
        }, status=status.HTTP_201_CREATED)

    def _prepare_booking_data(self, rBooking, billing_id):
        """Prepare booking data before serialization."""
        rBooking['customer_bill'] = billing_id
        rBooking['check_in'], rBooking['check_out'] = [
            datetime.fromisoformat(date.replace("Z", "+00:00")).strftime("%Y-%m-%d")
            for date in rBooking['dateRange']
        ]
        rBooking['status'] = 2
        rBooking['room'] = int(rBooking['roomNumber'])
        rBooking['room_type'] = int(rBooking['room_type'])
        rBooking['children_count'] = int(rBooking['children_count'])
        rBooking['adult_count'] = int(rBooking['adult_count'])

class RoomTypes(generics.ListAPIView):
    serializer_class = RoomTypeSerializer
    queryset = RoomType.objects.all()


class GetBookedRoomsNow(generics.ListAPIView):
    serializer_class = BookingSerializer

    def get_queryset(self):
        today = datetime.now().date()
        print(today)
        queryset = Booking.objects.filter(
            Q(status=2) & Q(check_in__lte=today) & Q(check_out__gte=today)
        )
        
        return queryset

class GetBookedNow(APIView):
    def get(self, request):
        today = datetime.now().date()
        rooms = Room.objects.all()

        data ={}
        for room in rooms:
            booking = Booking.objects.filter(room=room, check_in__lte=today, check_out__gte=today)
            
            
            if booking:
                serializedData = BookingSerializer(booking) 
                print(serializedData)
                print(booking)
        
        return Response(data)


# class RoomTypes(APIView):
#     def get(self, request):
#         types = RoomType.objects.all()
#         serializer = RoomTypeSerializer(types, many=True)
#         return Response(serializer.data, status=status.HTTP_200_OK)
    

# class ConfirmedBookings(generics.ListAPIView):
#     serializer_class = BookingSerializer
#     def get_queryset(self):
#         return super().get_queryset()
      