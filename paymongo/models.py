from django.db import models
from transactions.models import Billing

class WebhookEvent(models.Model):
    event_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    billing = models.ForeignKey(Billing, on_delete=models.CASCADE, null=True, blank=True)  # ForeignKey to Billing
    event_type = models.CharField(max_length=255)
    payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Event ID: {self.event_id} Webhook Event: {self.event_type} at {self.received_at}"


