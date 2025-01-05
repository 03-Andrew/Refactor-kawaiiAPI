from django.urls import path, include
from . import views

urlpatterns = [
    path("api/food/add/", views.AddFoodList.as_view(), name="add-food-list"),
    path("api/food/edit/<int:pk>/", views.ModifyFoodList.as_view(), name='modify-food-list'),
    
    path('api/activities/',views.ActivitiesList.as_view(),name = "activities"), 
    path('api/amenities/',views.AmenitiesList.as_view(),name = "amenities"), 

]