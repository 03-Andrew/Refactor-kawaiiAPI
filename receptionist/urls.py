from django.urls import path
from . import views
from .views import WebSocketTestView

urlpatterns = [
    #For viewing all amenities
    path('api/amenities/',views.AmenitiesList.as_view(),name = "amenities"), 
    #For viewing/adding all amenities availed
    path('api/amenities-availed/', views.AmenitiesListAvailed.as_view(), name="amenities-availed"), 
    #For deleting/updating amenities (not sure if this is needed?)
    path('api/amenities-availed-detail/<str:pk>/',views.AmenitiesDetailAvailed.as_view(),name = "amenities-detail-availed"), 
    
    #For viewing all activities
    path('api/activities/',views.ActivitiesList.as_view(),name = "activities"), 
    #For viewing/adding all activities availed
    path('api/activities-availed/', views.ActivitiesListAvailed.as_view(), name="activities-availed"), 
    #For deleting/updating activities (not sure if this is needed?)
    path('api/activities-availed-detail/<str:pk>/',views.ActivitiesDetailAvailed.as_view(),name = "activities-detail-availed"), 
    
    # To add both amenities and activities availed
    path('api/activites-amenities-availed/add/', views.AddAmenitiesAndActivitiesAvailed.as_view(), name="add-amenity-activity-availed"),

    # Test modified Payment if it works
    path('api/all-payments/', views.GetPayments.as_view(), name='get-payments'),
    
    # Websocket Testing
    path('api/trigger-websocket/', WebSocketTestView.as_view(), name='trigger_websocket')
]   