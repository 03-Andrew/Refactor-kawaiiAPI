from rest_framework import serializers
from django.contrib.auth.models import User
from .models import UserProfile


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['role']
    
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['role'] = instance.role 
        return representation
        
class UserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    class Meta(object):
        model = User
        fields = ['id', 'username', 'password', 'email', 'role']

    def get_role(self, obj):
        return obj.user_profile.role if obj.user_profile and obj.user_profile.role else None