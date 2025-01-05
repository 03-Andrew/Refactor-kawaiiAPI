from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework import status

from .serializers import FoodListSerializer, ActivitiesSerializer, AmenitiesSerializer
from .models import Food, Activity, Amenities

# Create your views here.
class ActivitiesList(generics.ListAPIView):
    queryset = Activity.objects.all()
    serializer_class = ActivitiesSerializer

class AmenitiesList(generics.ListCreateAPIView):
    queryset = Amenities.objects.all()
    serializer_class = AmenitiesSerializer


class AddFoodList(generics.ListCreateAPIView):
    serializer_class = FoodListSerializer
    queryset = Food.objects.all()

class ModifyFoodList(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = FoodListSerializer
    queryset = Food.objects.all()
    lookup_field = 'pk'

