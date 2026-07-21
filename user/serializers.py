from rest_framework import serializers
from django.contrib.auth.models import User
from .models import UserProfile


class UserLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


class UserAuthSerializer(UserLoginSerializer):
    email = serializers.EmailField()


class UserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'role']
        read_only_fields = fields

    def get_role(self, obj):
        try:
            return obj.user_profile.role
        except UserProfile.DoesNotExist:
            return None
