import requests
from kawaiiAPI.settings.base import PAYMONGO_PUBLIC_KEY, PAYMONGO_SECRET_KEY, PAYMONGO_WEBHOOK_SECRET
from rest_framework.views import APIView
from .serializers import PaymongoPaymentSerializer
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
import hmac
import hashlib
from rest_framework import status


class CreatePaymentQr(APIView):
    permission_classes=[AllowAny]
    authentication_classes=[]
    @extend_schema(
        tags=['Paymongo'],
        request=PaymongoPaymentSerializer
    )
    def post(self, request):
        serializer = PaymongoPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        payment_intent = self._create_payment_intent(data.get("amount"), data.get("description"))
        generate_qr = self._create_qr()
        functional_qr = self._attach_method_to_payment_intent(
            payment_intent_id=payment_intent["data"]['id'], 
            payment_method_id=generate_qr["data"]["id"]
        )
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

    def _create_payment_intent(self, amount: int, desc: str):
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

    def _attach_method_to_payment_intent(self, payment_intent_id, payment_method_id):
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

class CreateCheckoutSession(APIView):
    permission_classes=[AllowAny]
    authentication_classes=[]
    @extend_schema(
        tags=['Paymongo'],
        request=PaymongoPaymentSerializer
    )
    def post(self, request):
        serializer = PaymongoPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
    
        try:
            link = self._create_checkout_link(data.get("amount"), data.get("desc"))
            return Response(link)
        except Exception as e:
            return Response({
                "error": str(e) 
            })
        
    def _create_checkout_link(self, amount, desc):
        url = "https://api.paymongo.com/v1/checkout_sessions"
        payload = { 
            "data": { 
                "attributes": {
                    "line_items": [
                        {
                            "amount": amount,
                            "currency": "PHP",
                            "description": desc,
                            "name": "Booking Down payment",
                            "images": [],
                            "quantity": 1
                        }
                    ],
                    "payment_method_types": ["card", "gcash", "paymaya"]
                } } }
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
        }

        response = requests.post(url, json=payload, headers=headers, auth=(PAYMONGO_SECRET_KEY, ""))
        return response.json()


class WebhookNotif(APIView):
    permission_classes=[AllowAny]
    authentication_classes=[]
    @extend_schema(tags=['Paymongo'])
    def post(self, request, *args, **kwargs):
        if not self._validate_signature(request):
            return Response({'status': 'error', 'message': 'Invalid signature'}, status=status.HTTP_403_FORBIDDEN)
    
        return Response({'status': 'success'}, status=status.HTTP_200_OK)


    def _validate_signature(self, request):
        paymongo_signature = request.headers.get('Paymongo-Signature', None)
        if not paymongo_signature:
            return False

        sig_parts = {}
        for item in paymongo_signature.split(','):
            if '=' in item:
                key, value = item.split('=',1)
                sig_parts[key.strip()] = value.strip()

        
        timestamp = sig_parts.get('t')
        test_sig = sig_parts.get('te') or sig_parts.get('li')

        if not timestamp or not test_sig:
            return False
        
        raw_body = request.body
        signature_payload = f"{timestamp}.{raw_body.decode('utf-8')}"
        webhook_secret = PAYMONGO_WEBHOOK_SECRET

        computed_signature = hmac.new(
            webhook_secret.encode('utf-8'),
            signature_payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        print(test_sig)
        print(computed_signature)

        return hmac.compare_digest(computed_signature, test_sig)
