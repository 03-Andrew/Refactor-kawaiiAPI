from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import api_view
from bookings.models import Booking,Room
from transactions.models import Amenities, AmenitiesAvailed, Activity,ActivitiesAvailed
from .serializers import BookingsSerializer,RoomStatusListSerializer, RoomBookingListSerializer, RoomStatusSerializer,BookingsListSerializer, AmenitiesSerializer,AmenitiesAvailedSerializer, AmenitiesAvailedListSerializer, ActivitiesSerializer,ActivitiesAvailedSerializer, ActivitiesAvailedListSerializer
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
    serializer = BookingsListSerializer(bookings, many=True)
    return Response(serializer.data)

@api_view(['GET'])
def booking_list_approved(request):
    bookings = Booking.objects.filter(status='2')  # Filters booking (approved only)
    serializer = BookingsListSerializer(bookings, many=True)
    return Response(serializer.data)

class BookingDetailPending(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = BookingsSerializer
    primary_key = 'pk'
    queryset = Booking.objects.filter(status='1')  # Filters booking (pending only)

    def get_object(self):
        return generics.get_object_or_404(self.queryset, **{self.primary_key: self.kwargs['pk']})

@api_view(['GET'])
def amenities_list(request):
    amenities = Amenities.objects.all()
    serializer = AmenitiesSerializer(amenities, many=True)
    return Response(serializer.data)

class AmenitiesListAvailed(generics.ListCreateAPIView):
    queryset = AmenitiesAvailed.objects.all()

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return AmenitiesAvailedSerializer
        return AmenitiesAvailedListSerializer

class AmenitiesDetailAvailed(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AmenitiesAvailedSerializer
    primary_key = 'pk'
    queryset = AmenitiesAvailed.objects.all()


@api_view(['GET'])
def activities_list(request):
    amenities = Activity.objects.all()
    serializer = ActivitiesSerializer(amenities, many=True)
    return Response(serializer.data)

class ActivitiesListAvailed(generics.ListCreateAPIView):
    queryset = ActivitiesAvailed.objects.all()

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ActivitiesAvailedSerializer
        return ActivitiesAvailedListSerializer

class ActivitiesDetailAvailed(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ActivitiesAvailedSerializer
    primary_key = 'pk'
    queryset = ActivitiesAvailed.objects.all()
    
    

    