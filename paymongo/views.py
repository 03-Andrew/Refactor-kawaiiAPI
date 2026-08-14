import requests
from kawaiiAPI.settings.base import PAYMONGO_PUBLIC_KEY, PAYMONGO_SECRET_KEY
from rest_framework.views import APIView
from .serializers import PaymentIntent
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny

class CreatePaymentQr(APIView):
    permission_classes=[AllowAny]
    authentication_classes=[]
    @extend_schema(
        tags=['Paymongo'],
        request=PaymentIntent
    )
    def post(self, request):
        serializer = PaymentIntent(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        payment_intent = create_payment_intent(data.get("amount"), data.get("description"))
        generate_qr = self._create_qr()
        functional_qr = attach_method_to_payment_intent(
            payment_intent_id=payment_intent["data"]['id'], 
            payment_method_id=generate_qr["data"]["id"])
        return Response(functional_qr)
    
    def _create_qr(self):
        url = "https://api.paymongo.com/v1/payment_methods"
        header = {
            "accept": "application/json",
            "content-type": "application/json",
        }
        payload = {
            "data": {
                "attributes": {
                    "type": "qrph",
                    "expiry_seconds": 1800
                }
            }

        }
        try: 
            response = requests.post(url, headers=header, json=payload, auth=(PAYMONGO_PUBLIC_KEY, ""))
            return response.json()
        except Exception as e:
            return {
                'error': f'Failed to generate qr: {str(e)}'
            },

def create_payment_intent(amount: int, desc: str):
    url = "https://api.paymongo.com/v1/payment_intents"
    headers = {
        "accept": "application/json",
        "content-type": "application/json"
    }
    payload = { 
        "data": { 
            "attributes": {
                "capture_type": "automatic",
                "amount": amount,
                "payment_method_allowed": ["qrph"],
                "currency": "PHP",
                "description": desc
            } 
        } 
    }
    try: 
        response = requests.post(url, headers=headers, json=payload, auth=(PAYMONGO_SECRET_KEY, ""))
        return response.json()
    except Exception as e:
        return {
            'error': f'Failed to generate payment intent: {str(e)}'
        
        }

def attach_method_to_payment_intent(payment_intent_id, payment_method_id):
    url = f"https://api.paymongo.com/v1/payment_intents/{payment_intent_id}/attach"

    header = {
        "accept": "application/json",
        "content-Type": "application/json",
    }
    payload = {
        "data": {
            "attributes": {
                "payment_method": payment_method_id,
            }
        }
    }
    response = requests.post(url, headers=header, json=payload, auth=(PAYMONGO_SECRET_KEY, ""))
    return response.json()


