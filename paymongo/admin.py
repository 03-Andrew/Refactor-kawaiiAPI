from django.contrib import admin
from django.utils.html import format_html
import json
from .models import WebhookEvent

@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ('id','event_type', 'formatted_payload', 'received_at')  
    search_fields = ('event_type',)  
    ordering = ('-received_at',)

    def formatted_payload(self, obj):
        # Format the JSON payload to a readable string
        return format_html("<pre>{}</pre>", json.dumps(obj.payload, indent=2))

    formatted_payload.short_description = 'Payload' 
