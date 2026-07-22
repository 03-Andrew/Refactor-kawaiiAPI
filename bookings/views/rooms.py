
from datetime import date

from django.db.models import Count, Exists, OuterRef, Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.response import Response

from bookings.models import Booking, Room, RoomStatus, RoomType, BookingStatus
from bookings.serializers import RoomSerializer, RoomTypeSerializer, AvailableRoomSerializer2
from bookings.services.lock import get_locked_count

ROOM_QUERY_PARAMS = [
    OpenApiParameter('check_in', type=str, description='Filter available rooms (YYYY-MM-DD)'),
    OpenApiParameter('check_out', type=str, description='Filter available rooms (YYYY-MM-DD)'),
    OpenApiParameter('type', type=str, description='Filter by room type'),
    OpenApiParameter('sort', type=str, enum=['asc', 'desc'], description='Sort by room ID'),
    OpenApiParameter('include_booked', type=bool, description='Show all rooms with is_booked flag'),
]


class RoomListCreateView(generics.ListCreateAPIView):
    serializer_class = RoomSerializer

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
                queryset = queryset.annotate(
                    is_booked=Exists(
                        Booking.objects.filter(
                            room=OuterRef('pk'),
                            check_in__lt=check_out_date,
                            check_out__gt=check_in_date,
                        )
                    )
                )
            else:
                queryset = queryset.exclude(
                    Q(bookings__check_in__lt=check_out_date)
                    & Q(bookings__check_out__gt=check_in_date)
                ).distinct()
                
        elif include_booked:
            today = date.today()
            queryset = queryset.annotate(
                is_booked=Exists(
                    Booking.objects.filter(
                        room=OuterRef('pk'),
                        check_in__lte=today,
                        check_out__gt=today,
                    ).exclude(status=BookingStatus.CANCELLED)
                )
            )

        if room_type:
            queryset = queryset.filter(type__name__icontains=room_type)

        if sort_order == 'asc':
            queryset = queryset.order_by('id')
        elif sort_order == 'desc':
            queryset = queryset.order_by('-id')

        return queryset


class RoomDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Room.objects.all()
    serializer_class = RoomSerializer


class RoomTypesListView(generics.ListCreateAPIView):
    serializer_class = RoomTypeSerializer
    queryset = RoomType.objects.all()
    pagination_class = None

    @extend_schema(parameters=ROOM_QUERY_PARAMS[0:3])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        queryset = RoomType.objects.all()
        check_in = request.query_params.get('check_in')
        check_out = request.query_params.get('check_out')
        room_type = request.query_params.get('type')

        if room_type:
            queryset = queryset.filter(name__icontains=room_type)

        annotations = {
            'total_count': Count('room', distinct=True),
            'maintenance_count': Count('room', distinct=True, filter=Q(room__status=RoomStatus.MAINTENANCE)),
        }
        if check_in and check_out:
            try:
                check_in_date = date.fromisoformat(check_in)
                check_out_date = date.fromisoformat(check_out)
            except ValueError:
                return Response([])
            annotations['booked_count'] = Count(
                'bookings',
                filter=Q(bookings__check_in__lt=check_out_date)
                & Q(bookings__check_out__gt=check_in_date)
                & Q(bookings__status__in=[BookingStatus.APPROVED, BookingStatus.PENDING]),
                distinct=True,
            )
        else:
            annotations['booked_count'] = Count('bookings', distinct=True)

        queryset = queryset.annotate(**annotations)

        data = []
        for rt in queryset:
            serialized = self.get_serializer(rt).data
            locked = 0
            if check_in and check_out:
                try:
                    locked = get_locked_count(rt.id, check_in, check_out)
                except Exception:
                    pass
            serialized['total_rooms'] = rt.total_count
            serialized['booked_rooms'] = rt.booked_count
            serialized['locked_rooms'] = locked
            serialized['available_rooms'] = rt.total_count - rt.booked_count - rt.maintenance_count - locked
            serialized['maintenance_rooms'] = rt.maintenance_count
            data.append(serialized)
        return Response(data)


class RoomTypesDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = RoomTypeSerializer
    queryset = RoomType.objects.all()
