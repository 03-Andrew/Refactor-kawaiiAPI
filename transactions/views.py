from django.db.models import Q, Prefetch

from rest_framework.views import APIView
from rest_framework import generics
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny

# Models
from .models import Billing, Customer, GuestList, FoodBill, GuestStatus, Food, AdditionalPayment, BillingStatus

from kawaiiAPI.permissions import IsReceptionistOrAdmin, AdminDeleteOnly

# Serializers
from .serializers import (
    BillingSerializer, CustomerSerializer, BillingSerializerBase,
    GuestListSerializer, BillingDetailSerializer, FoodListSerializer,
    CreatePaymentSerializer, BillingLookupSerializer,
)
from transactions.serializers import FoodBillSerializer, AdditionalPaymentSerializer
from bookings.models import Booking
from transactions.models import AmenitiesAvailed, ActivitiesAvailed
from drf_spectacular.utils import extend_schema, OpenApiParameter
from bookings.services.booking import lookup_billing

@extend_schema(tags=['Billing'])
class BillingList(generics.ListAPIView):
    serializer_class = BillingSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    @extend_schema(
        parameters=[
            OpenApiParameter('name', type=str),
            OpenApiParameter('status',type=str,enum=BillingStatus.values, many=True),
        ]
    )
    def get(self, request, *args, **kwargs):
            return super().get(request, *args, **kwargs)
    
    def get_queryset(self):
        name = self.request.GET.get("name")
        statuses = self.request.GET.getlist("status")
        queryset = Billing.objects.select_related('customer').prefetch_related(
            Prefetch(
                'bookings',
                queryset=Booking.objects.select_related('room_type', 'room')
            ),
            Prefetch(
                'amenities_availed',
                queryset=AmenitiesAvailed.objects.select_related('amenity')
            ),
            Prefetch(
                'activities_availed',
                queryset=ActivitiesAvailed.objects.select_related('activity')
            ),
            'payment',
            'food_bill',
            'additional_payment',
        ).all()

        if statuses:
            queryset = queryset.filter(Q(status__in=statuses)).distinct()
        if name:
            queryset = queryset.filter(Q(customer__first_name__icontains=name) |
                            Q(customer__last_name__icontains=name))

        return queryset

@extend_schema(tags=['Billing'])
class BillingSingleEntity(generics.RetrieveUpdateAPIView):
    queryset = Billing.objects.all()
    serializer_class = BillingSerializerBase
    permission_classes = [IsReceptionistOrAdmin]

    lookup_field = 'pk' 

@extend_schema(tags=['Billing'])
class BillingDetails(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [AdminDeleteOnly]
    serializer_class = BillingDetailSerializer
    queryset = Billing.objects.prefetch_related(
        'bookings__customer_bill__customer',
        'bookings__room',
        'bookings__room_type',
        'amenities_availed__amenity',
        'activities_availed__activity',
        'food_bill',
        'additional_payment',
        'payment__mop',
    ).select_related('customer')
    lookup_field = 'pk'

@extend_schema(tags=['Billing'])
class BillingLookupView(APIView):
    """
    Public endpoint: look up a billing by billing_reference + customer email.
    Both must match. Returns only the room bookings under that billing.
    No authentication required — customers use this to view their own bookings.
    """
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['Billing'],
        description=(
            'Look up bookings by billing reference number and customer email. '
            'Both fields must match. Returns only the room bookings. '
            'No authentication required.'
        ),
    )
    def get(self, request, billing_reference, email, *args, **kwargs):

        billing = lookup_billing(billing_reference=billing_reference, email=email)

        if not billing:
            return Response(
                {'error': 'No billing found for the provided details.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(BillingLookupSerializer(billing).data, status=status.HTTP_200_OK)

@extend_schema(tags=['Customer'])
class CustomerList(generics.ListAPIView):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [IsReceptionistOrAdmin]

@extend_schema(tags=['Customer'])
class CustomerSingleEntity(generics.RetrieveUpdateDestroyAPIView):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [AdminDeleteOnly]


@extend_schema(
    tags=['Payments'],
    request=CreatePaymentSerializer,
    
)
class CreatePayment(APIView):
    permission_classes = [IsReceptionistOrAdmin]
    def post(self, request):
        serializer = CreatePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        created_payments = serializer.save()
        return Response({"created_payments": created_payments}, status=status.HTTP_201_CREATED)

@extend_schema(tags=['Guests'])
class GuestListView(generics.ListCreateAPIView):
    serializer_class = GuestListSerializer
    permission_classes = [IsReceptionistOrAdmin]

    def get_queryset(self):
        queryset = GuestList.objects.all()
        customer = self.request.GET.get('customer')
        customer_bill = self.request.GET.get('customer_bill')

        if customer:
            queryset = queryset.filter(
                Q(guest__icontains=customer) | 
                Q(guest__icontains=customer)
            )

        if customer_bill:
            queryset = queryset.filter(customer_bill=customer_bill)

        return queryset

@extend_schema(tags=['Guests'])
class GuestListSingleEntity(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = GuestListSerializer
    queryset = GuestList.objects.all()
    lookup_field = 'pk'
    permission_classes = [AdminDeleteOnly]

@extend_schema(tags=['Food'])
class AddFoodBill(generics.ListCreateAPIView):
    serializer_class = FoodBillSerializer
    permission_classes = [IsReceptionistOrAdmin]
    queryset = FoodBill.objects.all()
    
    # @method_decorator(csrf_protect)
    def perform_create(self, serializer):
        serializer.save()

@extend_schema(tags=['Food'])   
class ModifyFoodBill(generics.RetrieveUpdateAPIView):
    serializer_class = FoodBillSerializer
    queryset = FoodBill.objects.all()
    lookup_field = 'pk'
    permission_classes = [IsReceptionistOrAdmin]

@extend_schema(tags=['Food'])   
class AddFoodList(generics.ListCreateAPIView):
    serializer_class = FoodListSerializer
    permission_classes = [IsReceptionistOrAdmin]
    queryset = Food.objects.all()

@extend_schema(tags=['Food'])   
class ModifyFoodList(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = FoodListSerializer
    queryset = Food.objects.all()
    lookup_field = 'pk'
    permission_classes = [AdminDeleteOnly]

@extend_schema(tags=['Additional'])   
class AdditionalPayments(generics.ListCreateAPIView):
    serializer_class = AdditionalPaymentSerializer
    queryset = AdditionalPayment.objects.all()
    permission_classes = [IsReceptionistOrAdmin]


