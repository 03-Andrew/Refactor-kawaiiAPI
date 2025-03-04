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
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication


# Models
from .models import Billing, Customer, Payment, AmenitiesAvailed, GuestList, FoodBill, GuestStatus, Food, AdditonalPayment, ActivitiesAvailed
from bookings.models import Booking

# Serializers
from .serializers import BillingStatusSerializer, BillingSerializer, CustomerSerializer, PaymentSerializer, BillingSerializerBase, PendingBookings, BillingGuestList, GuestListSerializer, GuestListSerializerAll, BillingDetailSerializer, ConfirmedBooking, GuestStatusSerializer, FoodListSerializer
from transactions.serializers import FoodBillSerializer, AdditionalPaymentSerializer

# 1. List View - for listing all Billings
class BillingList(generics.ListAPIView):
    serializer_class = BillingSerializer

    def get_queryset(self):
        name = self.request.GET.get("name")
        queryset =  Billing.objects.all()

        if name:
            queryset = queryset.filter(Q(customer__first_name__icontains = name) |
                            Q(customer__last_name__icontains = name))
             
        return queryset

# 2. Create View - for creating a new Billing
class BillingCreate(generics.ListCreateAPIView):
    queryset = Billing.objects.all()
    serializer_class = BillingSerializerBase
    
    # @method_decorator(csrf_protect)
    def perform_create(self, serializer):
        # Add any custom logic for creation if necessary
        serializer.save()

# 3. Update View - for editing an existing Billing
class BillingUpdate(generics.RetrieveUpdateDestroyAPIView):
    queryset = Billing.objects.all()
    serializer_class = BillingSerializerBase
    lookup_field = 'pk' 

class BillingUpdate2(generics.RetrieveUpdateDestroyAPIView):
    queryset = Billing.objects.all()
    serializer_class = BillingStatusSerializer
    lookup_field = 'pk' 

class CustomerListCreate(generics.ListCreateAPIView):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer

class PaymentListCreate(generics.ListCreateAPIView):
    serializer_class = PaymentSerializer
    
    def get_queryset(self):
        queryset = Payment.objects.all()
        customer = self.request.query_params.get("customer_bill")

        if status:
            queryset = queryset.filter(customer_bill=customer)

        return queryset

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
                    serializer = PaymentSerializer(data=payment_data)
                    if serializer.is_valid():
                        payment = serializer.save()
                        created_payments.append(serializer.data)
                    else:
                        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        return Response({"created_payments": created_payments}, status=status.HTTP_201_CREATED)

        
class ListBillingBooking(generics.ListAPIView):
    # authentication_classes = [JWTAuthentication]
    # permission_classes = [IsAuthenticated]
    serializer_class = PendingBookings
    def get_queryset(self):
        queryset = Billing.objects.filter(Q(bookings__isnull=False) & Q(status_id__exact=3)).distinct()
        customer = self.request.GET.get('customer')  
        sort = self.request.GET.get('sort')

        # Filtering 
        if customer:
            queryset = queryset.filter(
                Q(customer__first_name__icontains=customer) | 
                Q(customer__last_name__icontains=customer)
            )

        # Sorting
        if sort:
            if sort == 'asccheckin':
                queryset = queryset.annotate(min_check_in=Min('bookings__check_in')).order_by('min_check_in')
            elif sort == 'desccheckin':
                queryset = queryset.annotate(min_check_in=Min('bookings__check_in')).order_by('-min_check_in')
            elif sort == 'asccheckout':
                queryset = queryset.annotate(min_check_out=Min('bookings__check_out')).order_by('min_check_out')
            elif sort == 'desccheckout':
                queryset = queryset.annotate(min_check_out=Min('bookings__check_out')).order_by('-min_check_out')

        return queryset

class ListConfirmedBooking(generics.ListAPIView):
    serializer_class = ConfirmedBooking
    def get_queryset(self):

        customer = self.request.GET.get('customer')
        booking_id = self.request.GET.get('id')
        check_in = self.request.GET.get('check_in')
        sort = self.request.GET.get('sort')
        status = self.request.GET.get('status')

        queryset = Booking.objects.filter(status=status).order_by("-check_out")

        #Filter
        if customer:
            queryset = queryset.filter(
                Q(customer_bill__customer__first_name__icontains=customer) | 
                Q(customer_bill__customer__last_name__icontains=customer)
            )

        if check_in:
            queryset = queryset.filter(check_in=check_in)

        if booking_id:
            queryset = queryset.filter(id=booking_id)

         # Annotate with availed_boat_transfer
        queryset = queryset.annotate(
            availed_boat_transfer=Subquery(
                AmenitiesAvailed.objects.filter(
                    customer_bill=OuterRef('customer_bill'),
                    amenity__amenity='boat transfer'
                ).values('time')[:1]
            )
        )

        # Sort
        if sort:
            if sort == 'asccheckin':
                queryset = queryset.order_by('check_in') 
            elif sort == 'desccheckin':
                queryset = queryset.order_by('-check_in')
            elif sort == 'asccheckout':
                queryset = queryset.order_by('check_out') 
            elif sort == 'desccheckout':
                queryset = queryset.order_by('-check_out')
            elif sort == 'ascroom':
                queryset = queryset.annotate(num_int=Cast('number', IntegerField())).order_by('num_int')
            elif sort == 'descroom':
                queryset = queryset.annotate(num_int=Cast('number', IntegerField())).order_by('-num_int')
            elif sort == 'ascboat':
                queryset = queryset.order_by('availed_boat_transfer')  # Sort by annotated field
            elif sort == 'descboat':
                queryset = queryset.order_by('-availed_boat_transfer')  # Sort by annotated field
 
        return queryset
    
class EditBooking(generics.RetrieveUpdateAPIView):
    serializer_class = ConfirmedBooking
    lookup_field = 'pk'
    queryset = Booking.objects.all()
    
class GuestListView(generics.ListCreateAPIView):
    # queryset = GuestList.objects.all()
    serializer_class = GuestListSerializerAll
    def get_queryset(self):
        sort = self.request.GET.get('sort')
        queryset = GuestList.objects.filter(Q(customer_bill__status__status="processing") | Q(customer_bill__status__status="confirmed"))
        customer = self.request.GET.get('customer')

        if customer:
            queryset = queryset.filter(
                Q(guest__icontains=customer) | 
                Q(guest__icontains=customer)
            )
        return queryset

class UpdateGuestListStatus(APIView):
    def get(self, request, format=None):    
        return Response({"message": "Use POST to submit amenities and activities."}, status=200)

    def patch(self, request, *args, **kwargs):
        newStatus = request.data.get('newStatus', [])
        response_data = []
        for data in newStatus:
            print(data)
            guest_id = data.get('id')
            try:
                guest = GuestList.objects.get(id=guest_id)
                print(guest.guest)
            except GuestList.DoesNotExist:
                return Response({"detail": f"Guest {guest_id} does not exist."}, status=status.HTTP_404_NOT_FOUND)

            serializer = GuestListSerializer(guest, data=data, partial=True)
            if serializer.is_valid():
                serializer.save()
                response_data.append(serializer.data)  # Append each updated guest's data to response_data
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        return Response({"newStatus": response_data}, status=status.HTTP_200_OK)



class GuestListPerBilling(generics.RetrieveUpdateDestroyAPIView):
    queryset = Billing.objects.all()
    serializer_class = BillingGuestList
    lookup_field = 'pk'

class AddGuest(generics.ListCreateAPIView):
    queryset = GuestList.objects.all()
    serializer_class = GuestListSerializerAll
    
    
class EditGuestListStatus(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = GuestListSerializer
    queryset = GuestList.objects.all()
    lookup_field = 'pk'

class ActiveBookings(generics.ListCreateAPIView):
    serializer_class = BillingSerializer
    
    def get_queryset(self):
        return Billing.objects.filter(status=1)
    
class GetGuestStatus(generics.ListAPIView):
    serializer_class = GuestStatusSerializer
    queryset = GuestStatus.objects.all()

class BillingDetails(generics.RetrieveAPIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = BillingDetailSerializer
    queryset = Billing.objects.all()
    lookup_field = 'pk'


class AddFoodBill(generics.ListCreateAPIView):
    serializer_class = FoodBillSerializer
    queryset = FoodBill.objects.all()
    
    # @method_decorator(csrf_protect)
    def perform_create(self, serializer):
        serializer.save()
    
class ModifyFoodBill(generics.RetrieveUpdateAPIView):
    serializer_class = FoodBillSerializer
    queryset = FoodBill.objects.all()
    lookup_field = 'pk'

class AddFoodList(generics.ListCreateAPIView):
    serializer_class = FoodListSerializer
    queryset = Food.objects.all()

class ModifyFoodList(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = FoodListSerializer
    queryset = Food.objects.all()
    lookup_field = 'pk'

class CreateAdditionalPayments(generics.ListCreateAPIView):
    serializer_class = AdditionalPaymentSerializer
    queryset = AdditonalPayment.objects.all()


