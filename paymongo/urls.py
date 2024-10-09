from django.urls import path
#from .views import payment_page, AttachPaymentMethod,CreatePaymentIntent, CreateCardPaymentMethod, CreateGCashSource, GCashWebhook
from .views import CardPayment
#from .views import WebhookNotif, PaymentIntentList

urlpatterns = [
    # For posting card payments
    path('api/payment-card/', CardPayment.as_view(), name='create_payment_card'), #FINAL
]
