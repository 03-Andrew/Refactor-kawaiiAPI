from django.shortcuts import render

# Create your views here.
from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import api_view
from bookings.models import Booking
from .serializers import PendingBookingsSerializer
from rest_framework import generics

# Create your views here.

@api_view(['GET'])
def booking_list_pending(request):
    bookings = Booking.objects.filter(status='1')  # Filters booking (pending only)
    serializer = PendingBookingsSerializer(bookings, many=True)
    return Response(serializer.data)

class BookingDetailPending(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PendingBookingsSerializer
    primary_key = 'pk'
    queryset = Booking.objects.filter(status='1')  # Filters booking (pending only)

    def get_object(self):
        return generics.get_object_or_404(self.queryset, **{self.primary_key: self.kwargs['pk']})
    
    