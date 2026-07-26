from django.shortcuts import render
from django.db.models import Q, Subquery, OuterRef, IntegerField, Min
from django.contrib.contenttypes.models import ContentType
from django.utils.timezone import make_aware
from django.db.models.functions import Cast

from rest_framework.views import APIView
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework import status

from datetime import datetime

# Auth
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication


# Models
from .models import Billing, Customer, Payment, AmenitiesAvailed, GuestList, FoodBill, GuestStatus, Food, AdditonalPayment, ActivitiesAvailed, BillingStatus
from bookings.models import Booking

# Serializers
from .serializers import BillingSerializer, CustomerSerializer, PaymentBaseSerializer, BillingSerializerBase, GuestListSerializer, BillingDetailSerializer, FoodListSerializer
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


@extend_schema(tags=['Payments'])
class CreatePayment(APIView):
    def post(self, request):
        data = request.data
        customer_info = data.get("customerInfo", {})
        amount = data.get("amount", 0)
        selected_items = data.get("selectedItems", {})

        # Get common payment fields
        customer_bill_id = customer_info.get("customer_bill")
        date = make_aware(datetime.strptime(customer_info.get("date"), "%Y-%m-%d"))
        mop_id = customer_info.get("mop")
        status_id = customer_info.get("status")

        created_payments = []
        
        # Mapping of selected items to their content type and paymentFor value
        item_mapping = {
            "selectedRooms": {"model": Booking, "payment_for_id": 2},
            "selectedActivities": {"model": ActivitiesAvailed, "payment_for_id": 5},
            "selectedAmenities": {"model": AmenitiesAvailed, "payment_for_id": 4},
            "selectedFoodBills": {"model": FoodBill, "payment_for_id": 3},
            "selectedAdditionalPayments": {"model": AdditonalPayment, "payment_for_id": 6},
        }

        for key, config in item_mapping.items():
            item_ids = selected_items.get(key, [])
            print(item_ids)
            if item_ids:
                content_type = ContentType.objects.get_for_model(config["model"])
                
                for item in item_ids:  # item_ids is expected to be a list of dicts like [{id: 9, price: 22500}, ...]
                    object_id = item['id']          # Get the id from the dict
                    amount = item.get('price', item.get('subtotal'))  
                    payment_data = {
                        "customer_bill": customer_bill_id,
                        "amount": amount,            # Set the amount from the price
                        "date": date,
                        "mop": mop_id,
                        "paymentFor": config["payment_for_id"],
                        "status": status_id,
                        "content_type": content_type.id,
                        "object_id": object_id,
                    }
                    serializer = PaymentBaseSerializer(data=payment_data)
                    if serializer.is_valid():
                        payment = serializer.save()
                        created_payments.append(serializer.data)
                    else:
                        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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


