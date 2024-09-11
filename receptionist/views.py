from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import api_view
from bookings.models import Booking,Room, RoomType, RoomStatus
from .serializers import PendingBookingsSerializer,RoomStatusListSerializer, RoomBookingListSerializer, RoomStatusSerializer,PendingBookingsListSerializer
from rest_framework import generics
from datetime import date

# Create your views here.

@api_view(['GET'])
def room_list_status(request):
    rooms = Room.objects.all()
    serializer = RoomStatusListSerializer(rooms, many=True)
    return Response(serializer.data)

class RoomDetailStatus(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = RoomStatusSerializer
    primary_key = 'pk'
    queryset = Room.objects.all()

@api_view(['GET'])
def room_booking_list(request):
    rooms = Room.objects.all()
    serializer = RoomBookingListSerializer(rooms, many=True)
    return Response(serializer.data)

@api_view(['GET'])
def booking_list_pending(request):
    bookings = Booking.objects.filter(status='1')  # Filters booking (pending only)
    serializer = PendingBookingsListSerializer(bookings, many=True)
    return Response(serializer.data)

@api_view(['GET'])
def booking_list_approved(request):
    bookings = Booking.objects.filter(status='2')  # Filters booking (approved only)
    serializer = PendingBookingsListSerializer(bookings, many=True)
    return Response(serializer.data)

class BookingDetailPending(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PendingBookingsSerializer
    primary_key = 'pk'
    queryset = Booking.objects.filter(status='1')  # Filters booking (pending only)

    def get_object(self):
        return generics.get_object_or_404(self.queryset, **{self.primary_key: self.kwargs['pk']})

    
    