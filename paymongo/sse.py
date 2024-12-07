from django.http import JsonResponse
from django_eventstream import send_event

def payment_successful():
    # Trigger an SSE event to the "payments" channel
    send_event('payments', 'payment_success', {
        'message': 'Payment successful!',
    })

def trigger_payment(request):
    payment_successful()
    return JsonResponse({'status': 'success', 'message': 'SSE event sent!'})

