
from datetime import date

from django.db.models import Count, Exists, OuterRef, Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from kawaiiAPI.permissions import IsAdmin, IsReceptionistOrAdmin, ReceptionistViewOnly
from rest_framework.response import Response

from bookings.models import Booking, Room, RoomStatus, RoomType, BookingStatus
from bookings.serializers import RoomSerializer, RoomTypeSerializer, RoomTypeAvailabilitySerializer
from bookings.services.lock import bulk_get_locked_counts
from bookings.services.availability import get_room_types_availability

ROOM_QUERY_PARAMS = [
    OpenApiParameter('check_in', type=str, description='Filter available rooms (YYYY-MM-DD)'),
    OpenApiParameter('check_out', type=str, description='Filter available rooms (YYYY-MM-DD)'),
    OpenApiParameter('guest_count', type=int, description='Number of guests'),
    OpenApiParameter('type', type=str, description='Filter by room type'),
    OpenApiParameter('sort', type=str, enum=['asc', 'desc'], description='Sort by room ID'),
    OpenApiParameter('include_booked', type=bool, description='Show all rooms with is_booked flag'),
]


@extend_schema(tags=['Rooms'])
class RoomListCreateView(generics.ListCreateAPIView):
    serializer_class = RoomSerializer
    permission_classes = [ReceptionistViewOnly]

    @extend_schema(parameters=ROOM_QUERY_PARAMS)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        queryset = Room.objects.select_related('type')
        check_in = self.request.query_params.get('check_in')
        check_out = self.request.query_params.get('check_out')
        room_type = self.request.query_params.get('type')
        sort_order = self.request.query_params.get('sort')
        include_booked = self.request.query_params.get('include_booked', '').lower() == 'true'

        if not include_booked:
            queryset = queryset.filter(status=RoomStatus.AVAILABLE)

        if check_in and check_out:
            try:
                check_in_date = date.fromisoformat(check_in)
                check_out_date = date.fromisoformat(check_out)
            except ValueError:
                return Response({"error": "check_in/check_out must be valid ISO dates."}, status=400)

        if include_booked:
            if check_in and check_out:
                booking_filter = Q(
                    room=OuterRef('pk'),
                    check_in__lt=check_out_date,
                    check_out__gt=check_in_date,
                )
            else:
                today = date.today()
                booking_filter = Q(
                    room=OuterRef('pk'),
                    check_in__lte=today,
                    check_out__gt=today,
                ) & ~Q(status=BookingStatus.CANCELLED)
            queryset = queryset.annotate(
                is_booked=Exists(Booking.objects.filter(booking_filter)),
            )
        elif check_in and check_out:
            queryset = queryset.exclude(
                Q(bookings__check_in__lt=check_out_date)
                & Q(bookings__check_out__gt=check_in_date)
            ).distinct()

        if room_type:
            queryset = queryset.filter(type__name__icontains=room_type)

        if sort_order == 'asc':
            queryset = queryset.order_by('id')
        elif sort_order == 'desc':
            queryset = queryset.order_by('-id')

        return queryset


@extend_schema(tags=['Rooms'])
class RoomDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Room.objects.all()
    serializer_class = RoomSerializer
    permission_classes = [ReceptionistViewOnly]


@extend_schema(tags=['Room Types'])
class RoomTypesListView(generics.ListCreateAPIView):
    serializer_class = RoomTypeSerializer
    queryset = RoomType.objects.all()
    pagination_class = None

    def get_authenticators(self):
        if self.request and self.request.method == 'GET':
            return []
        return super().get_authenticators()
    
    def get_permissions(self):
        if self.request and self.request.method == 'GET':
            return [AllowAny()]
        return [IsAdmin()]

    def get_serializer_class(self):                                                                                                                                           
        if self.request and self.request.method == 'POST':                                                                                                                    
            return RoomTypeSerializer                                                                                                                                         
        return RoomTypeAvailabilitySerializer           

    
    @extend_schema(parameters=ROOM_QUERY_PARAMS[0:4])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        check_in = request.query_params.get('check_in')
        check_out = request.query_params.get('check_out')
        room_type = request.query_params.get('type')
        guest_count_param = request.query_params.get('guest_count') 

        try:
            guest_count = int(guest_count_param) if guest_count_param is not None else 1
            if guest_count < 1:
                return Response({'error': 'guest_count must be at least 1'}, status=status.HTTP_400_BAD_REQUEST)   
        
            room_types_availability = get_room_types_availability(
                check_in=check_in, check_out=check_out, room_type=room_type, guest_count=guest_count
            )
            
        except ValueError:
            return Response({'error': 'guest_count must be an integer'}, status=status.HTTP_400_BAD_REQUEST)
        data = []                                                                                                                            
        for item in room_types_availability:       
            serialized = self.get_serializer(item['room_type']).data                                                                         
            serialized.update({                                                                                                              
                'total_rooms': item['total_rooms'],                                                                                          
                'booked_rooms': item['booked_rooms'],                                                                                        
                'locked_rooms': item['locked_rooms'],                                                                                        
                'available_rooms': item['available_rooms'],                                                                                  
                'maintenance_rooms': item['maintenance_rooms'],
                'suggested_number_of_rooms_to_book':  item['suggested_number_of_rooms_to_book'],
                'should_add_extra_guest': item['should_add_extra_guest'],
                'pair_with_other_rooms': item['pair_with_other_rooms'],

            })                                                                                                                               
            data.append(serialized)  

        return Response(data)


@extend_schema(tags=['Room Types'])
class RoomTypesDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = RoomTypeSerializer
    queryset = RoomType.objects.all()
    def get_permissions(self):
        if self.request and self.request.method == "GET":
            return [AllowAny()]
        return [IsReceptionistOrAdmin]
    
    def get_authenticators(self):
        if self.request and self.request.method == "GET":
            return []
        return super().get_authenticators()