from django.db.models import Q
from rest_framework import generics, status
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from django.db import transaction

from transactions.models import AmenitiesAvailed, ActivitiesAvailed, Payment
from transactions.serializers import (
    AmenitiesAvailedSerializer,
    ActivitiesAvailedSerializer,
)
from receptionist.serializers import (
    AmenitiesAvailedListSerializer,
    ActivitiesAvailedListSerializer,
    PaymentSerializer,
)
from kawaiiAPI.permissions import IsReceptionistOrAdmin


# ── V0 Unoptimized Querysets (without select_related / prefetch_related) ──────

def get_amenitiesavailedqueryset_v0(request):
    queryset = AmenitiesAvailed.objects.all()
    customer_name = request.GET.get('customer')

    if customer_name is not None:
        queryset = queryset.filter(
            Q(customer_bill__customer__first_name__icontains=customer_name) |
            Q(customer_bill__customer__last_name__icontains=customer_name)
        )

    return queryset


def get_activitiesavailedqueryset_v0(request):
    queryset = ActivitiesAvailed.objects.all()
    customer_name = request.GET.get('customer')

    if customer_name:
        queryset = queryset.filter(
            Q(customer_bill__customer__first_name__icontains=customer_name) |
            Q(customer_bill__customer__last_name__icontains=customer_name)
        )

    return queryset


# ── V0 Unoptimized Views ──────────────────────────────────────────────────────

@extend_schema(tags=['Amenities v0'])
class AmenitiesListAvailedV0(generics.ListCreateAPIView):
    queryset = AmenitiesAvailed.objects.all()
    permission_classes = [IsReceptionistOrAdmin]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return AmenitiesAvailedSerializer
        return AmenitiesAvailedListSerializer

    def create(self, request, *args, **kwargs):
        if isinstance(request.data, dict):
            amenities_data = [request.data]
        elif isinstance(request.data, list):
            amenities_data = request.data
        else:
            return Response({'error': 'Expected a list of amenities.'}, status=status.HTTP_400_BAD_REQUEST)

        created_amenities = []
        with transaction.atomic():
            for amenity_data in amenities_data:
                serializer = self.get_serializer(data=amenity_data)
                serializer.is_valid(raise_exception=True)
                self.perform_create(serializer)
                created_amenities.append(serializer.data)

        return Response(created_amenities, status=status.HTTP_201_CREATED)

    def get_queryset(self):
        return get_amenitiesavailedqueryset_v0(self.request)


@extend_schema(tags=['Activities v0'])
class ActivitiesListAvailedV0(generics.ListCreateAPIView):
    queryset = ActivitiesAvailed.objects.all()
    permission_classes = [IsReceptionistOrAdmin]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ActivitiesAvailedSerializer
        return ActivitiesAvailedListSerializer

    def create(self, request, *args, **kwargs):
        if isinstance(request.data, dict):
            activities_data = [request.data]
        elif isinstance(request.data, list):
            activities_data = request.data
        else:
            return Response({'error': 'Expected a list of amenities.'}, status=status.HTTP_400_BAD_REQUEST)

        created_amenities = []
        with transaction.atomic():
            for amenity_data in activities_data:
                serializer = self.get_serializer(data=amenity_data)
                serializer.is_valid(raise_exception=True)
                self.perform_create(serializer)
                created_amenities.append(serializer.data)

        return Response(created_amenities, status=status.HTTP_201_CREATED)

    def get_queryset(self):
        return get_activitiesavailedqueryset_v0(self.request)


@extend_schema(tags=['Payments v0'])
class GetPaymentsV0(generics.ListCreateAPIView):
    permission_classes = [IsReceptionistOrAdmin]
    serializer_class = PaymentSerializer

    def get_queryset(self):
        queryset = Payment.objects.all()
        mop = self.request.GET.get('mop')
        customer = self.request.GET.get('customer')
        sort = self.request.GET.get('sort')

        if mop:
            mop_list = mop.split(',')
            queryset = queryset.filter(mop__mode__in=[mode.strip() for mode in mop_list])

        if customer:
            queryset = queryset.filter(
                Q(customer_bill__customer__first_name__icontains=customer) |
                Q(customer_bill__customer__last_name__icontains=customer)
            )

        if sort:
            if sort == 'ascdate':
                queryset = queryset.order_by('date')
            elif sort == 'descdate':
                queryset = queryset.order_by('-date')

        return queryset
