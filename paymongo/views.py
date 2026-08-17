import requests
from kawaiiAPI.settings.base import PAYMONGO_PUBLIC_KEY, PAYMONGO_SECRET_KEY, PAYMONGO_WEBHOOK_SECRET
from rest_framework.views import APIView
from .serializers import PaymongoPaymentSerializer
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
import hmac
import hashlib
import json
from rest_framework import status
from transactions.models import Billing
from .tasks import process_event


def billing_fee_breakdown(billing):
    room_total = sum(b.total_cost for b in billing.bookings.all())
    boat = billing.amenities_availed.first()
    boat_total = boat.total_cost if boat else 0
    return room_total, boat_total, (boat.head_count if boat else 0)


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
        try:
            billing = Billing.objects.get(id=data.get("billing_id"))
        except Billing.DoesNotExist:
            return Response({"error": "Billing not found"}, status=status.HTTP_400_BAD_REQUEST)
        room_total, boat_total, _ = billing_fee_breakdown(billing)
        amount = int((room_total + boat_total) * 100)
        payment_intent = self._create_payment_intent(amount, data.get("description") or str(billing.id))
        generate_qr = self._create_qr()
        functional_qr = self._attach_method_to_payment_intent(
            payment_intent_id=payment_intent["data"]['id'], 
            payment_method_id=generate_qr["data"]["id"]
        )
        print(functional_qr)
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
        success_url = request.data.get("success_url")
        cancel_url = request.data.get("cancel_url")

        try:
            billing = Billing.objects.get(id=data.get("billing_id"))
            link = create_checkout_link(billing, data.get("description"), success_url, cancel_url)
            return Response(link)
        except Billing.DoesNotExist:
            return Response({"error": "Billing not found"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                "error": str(e)
            })

def create_checkout_link(billing, desc, success_url=None, cancel_url=None):
    url = "https://api.paymongo.com/v1/checkout_sessions"
    boat_total = sum(a.total_cost for a in billing.amenities_availed.all())
    line_items = [
        {
            "amount": int(booking.total_cost * 100),
            "currency": "PHP",
            "description": "room_fee",
            "name": f"{booking.room_type.name} Room",
            "quantity": 1,
        }
        for booking in billing.bookings.all()
    ]
    if boat_total:
        boat = billing.amenities_availed.first()
        line_items.append({
            "amount": int(boat.amenity.rate_per_head * 100),
            "currency": "PHP",
            "description": "boat_fee",
            "name": "Boat",
            "quantity": boat.head_count,
        })
    attributes = {
        "line_items": line_items,
        "payment_method_types": ["card", "gcash", "paymaya", "qrph"],
        "description": desc or str(billing.id),
        "send_email_receipt": True,
        "show_description": True,
        "show_line_items": True,
    }
    if success_url:
        attributes["success_url"] = success_url
    if cancel_url:
        attributes["cancel_url"] = cancel_url
    payload = {
        "data": {
            "attributes": attributes
        }
    }
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

        process_event.delay(json.loads(request.body))
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
