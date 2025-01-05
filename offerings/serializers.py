from rest_framework import serializers
from .models import Food, Activity, Amenities


class ActivitiesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Activity
        fields = '__all__'

class AmenitiesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Amenities
        fields = '__all__'

class FoodListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Food
        fields = '__all__'

    