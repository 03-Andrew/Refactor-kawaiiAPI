from django.db.models import Q

from rest_framework.views import APIView
from rest_framework import generics
from rest_framework.response import Response
from rest_framework import status

# Models
from .models import Billing, Customer, GuestList, FoodBill, GuestStatus, Food, AdditonalPayment, BillingStatus

# Serializers
from .serializers import (
    BillingSerializer, CustomerSerializer, BillingSerializerBase,
    GuestListSerializer, BillingDetailSerializer, FoodListSerializer,
    CreatePaymentSerializer,
)
from transactions.serializers import FoodBillSerializer, AdditionalPaymentSerializer

from drf_spectacular.utils import extend_schema, OpenApiParameter

@extend_schema(tags=['Billing'])
class BillingList(generics.ListAPIView):
    serializer_class = BillingSerializer

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
            'bookings__room_type',
            'payment',
            'food_bill',
            'amenities_availed__amenity',
            'activities_availed__activity',
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
    lookup_field = 'pk' 

@extend_schema(tags=['Billing'])
class BillingDetails(generics.RetrieveAPIView):
    # authentication_classes = [JWTAuthentication]
    # permission_classes = [IsAuthenticated]
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

@extend_schema(tags=['Customer'])
class CustomerList(generics.ListAPIView):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer

@extend_schema(tags=['Customer'])
class CustomerSingleEntity(generics.RetrieveUpdateDestroyAPIView):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer


@extend_schema(
    tags=['Payments'],
    request=CreatePaymentSerializer,
    
)
class CreatePayment(APIView):
    def post(self, request):
        serializer = CreatePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        created_payments = serializer.save()
        return Response({"created_payments": created_payments}, status=status.HTTP_201_CREATED)

@extend_schema(tags=['Guests'])
class GuestListView(generics.ListCreateAPIView):
    serializer_class = GuestListSerializer

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

@extend_schema(tags=['Guests'])
class GuestListSingleEntity(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = GuestListSerializer
    queryset = GuestList.objects.all()
    lookup_field = 'pk'


@extend_schema(tags=['Food'])
class AddFoodBill(generics.ListCreateAPIView):
    serializer_class = FoodBillSerializer
    queryset = FoodBill.objects.all()
    
    # @method_decorator(csrf_protect)
    def perform_create(self, serializer):
        serializer.save()

@extend_schema(tags=['Food'])   
class ModifyFoodBill(generics.RetrieveUpdateAPIView):
    serializer_class = FoodBillSerializer
    queryset = FoodBill.objects.all()
    lookup_field = 'pk'

@extend_schema(tags=['Food'])   
class AddFoodList(generics.ListCreateAPIView):
    serializer_class = FoodListSerializer
    queryset = Food.objects.all()

@extend_schema(tags=['Food'])   
class ModifyFoodList(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = FoodListSerializer
    queryset = Food.objects.all()
    lookup_field = 'pk'

@extend_schema(tags=['Additional'])   
class AdditionalPayments(generics.ListCreateAPIView):
    serializer_class = AdditionalPaymentSerializer
    queryset = AdditonalPayment.objects.all()


