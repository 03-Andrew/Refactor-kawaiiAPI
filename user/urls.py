from django.contrib import admin
from django.urls import re_path, path
from . import views

from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)


urlpatterns = [
    re_path('api/login', views.login),
    re_path('api/signup', views.signup),
    re_path('api/test_token', views.test_token),
    re_path('api/tt2', views.get_user),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
]
