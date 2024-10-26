# receptionist/consumers.py

from channels.generic.websocket import WebsocketConsumer
import json
from asgiref.sync import async_to_sync

class ReceptionistConsumer(WebsocketConsumer):
    def connect(self):
        self.accept()

        # Join receptionist group to receive booking notifications
        async_to_sync(self.channel_layer.group_add)(
            "receptionist",
            self.channel_name
        )

    def disconnect(self, close_code):
        # Leave the receptionist group on disconnect
        async_to_sync(self.channel_layer.group_discard)(
            "receptionist",
            self.channel_name
        )
        
    def receive(self, text_data):
        data = json.loads(text_data)
        self.send(text_data=json.dumps({
            'message': 'Hello from WebSocket!'
        }))

    # Handle custom event type 'booking_paid'
    def booking_paid(self, event):
        message = event['message']

        # Send the message to WebSocket
        self.send(text_data=json.dumps({
            'message': message
        }))
