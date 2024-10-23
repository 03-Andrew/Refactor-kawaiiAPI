# receptionist/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer

class BookingConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_group_name = 'booking_notifications'
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Receive message from WebSocket
    async def receive(self, text_data):
        await self.send(text_data=json.dumps({
            'message': text_data
        }))

    # Send message to WebSocket
    async def booking_notification(self, event):
        message = event['message']
        await self.send(text_data=json.dumps({
            'message': message
        }))
