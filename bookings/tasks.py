from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
import logging

@shared_task
def send_email(subject, message, recipient_list):
    try:
        return send_mail(
            subject,
            message,
            settings.EMAIL_HOST_USER, 
            recipient_list,
            fail_silently=False,
        )
    except Exception as e:
        logging.error(f"Error sending email: {str(e)}")
