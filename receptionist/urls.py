from django.urls import path
from . import views
from . import views_v0
from .views import WebSocketTestView

urlpatterns = [
    # v0 endpoints (unoptimized, without select_related / prefetch_related)
    path('api/v0/amenities-availed/', views_v0.AmenitiesListAvailedV0.as_view(), name="v0-amenities-availed"),
    path('api/v0/activities-availed/', views_v0.ActivitiesListAvailedV0.as_view(), name="v0-activities-availed"),
    path('api/v0/all-payments/', views_v0.GetPaymentsV0.as_view(), name='v0-get-payments'),

    #For viewing all amenities
    path('api/amenities/',views.AmenitiesList.as_view(),name = "amenities"), 
    #For viewing/adding all amenities availed
    path('api/amenities-availed/', views.AmenitiesListAvailed.as_view(), name="amenities-availed"), 

    #For viewing all activities
    path('api/activities/',views.ActivitiesList.as_view(),name = "activities"), 
    #For viewing/adding all activities availed
    path('api/activities-availed/', views.ActivitiesListAvailed.as_view(), name="activities-availed"), 
    
    # To add both amenities and activities availed
    path('api/activites-amenities-availed/add/', views.AddAmenitiesAndActivitiesAvailed.as_view(), name="add-amenity-activity-availed"),

    # Test modified Payment if it works
    path('api/all-payments/', views.GetPayments.as_view(), name='get-payments'),
    
    # Websocket Testing
    path('api/trigger-websocket/', WebSocketTestView.as_view(), name='trigger_websocket')
]   