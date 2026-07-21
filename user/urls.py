from django.contrib import admin
from django.urls import re_path, path
from . import views

from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)


urlpatterns = [
    path('api/login', views.login),
    path('api/signup', views.signup),
    path('api/test_token', views.test_token),
    path('api/me', views.get_user),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]
