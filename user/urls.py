from django.contrib import admin
from django.urls import re_path
from . import views

urlpatterns = [
    re_path('api/login', views.login),
    re_path('api/signup', views.signup),
    re_path('api/test_token', views.test_token),
    re_path('api/tt2', views.get_user),
    
]
