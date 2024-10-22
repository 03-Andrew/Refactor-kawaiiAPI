# import json

# from channels.db import database_sync_to_async
# from djangochannelsrestframework.generics import GenericAsyncAPIConsumer
# from djangochannelsrestframework.observer import model_observer
# from djangochannelsrestframework.observer.generics import ObserverModelInstanceMixin, action

# from .models import Booking, Room, User
# from .serializers import BookingSerializer, RoomSerializer


# class BookingConsumer(ObserverModelInstanceMixin, GenericAsyncAPIConsumer):
#     queryset = Booking.objects.all()
#     serializer_class = BookingSerializer
#     lookup_field = "pk"

#     async def disconnect(self, code):
#         await super().disconnect(code)

#     @model_observer(Booking)
#     async def booking_activity(self, message, observer=None, subscribing_request_ids=[], **kwargs):
#         """
#         Sends real-time booking data to admins when a booking is made.
#         """
#         for request_id in subscribing_request_ids:
#             message_body = dict(request_id=request_id)
#             message_body.update(message)
#             await self.send_json(message_body)

#     @booking_activity.groups_for_signal
#     def booking_activity(self, instance: Booking, **kwargs):
#         yield 'room__{instance.room_id}'
#         yield f'pk__{instance.pk}'
#         yield 'admin_updates'

#     @booking_activity.groups_for_consumer
#     def booking_activity(self, room=None, **kwargs):
#         yield 'admin_updates'

#     @booking_activity.serializer
#     def booking_activity(self, instance: Booking, action, **kwargs):
#         """
#         Serializes the booking instance and sends it to the admin page.
#         """
#         return dict(data=BookingSerializer(instance).data, action=action.value, pk=instance.pk)

#     async def notify_admins(self, booking: Booking):
#         """
#         Sends a notification to the admin group about the new booking.
#         """
#         await self.channel_layer.group_send(
#             'admin_updates',
#             {
#                 'type': 'booking_notification',
#                 'booking': await self.serialize_booking(booking),
#             }
#         )

#     async def booking_notification(self, event: dict):
#         """
#         Sends the booking data to the WebSocket clients (admin page).
#         """
#         await self.send(text_data=json.dumps({'booking': event["booking"]}))

#     @database_sync_to_async
#     def get_room(self, pk: int) -> Room:
#         return Room.objects.get(pk=pk)

#     @database_sync_to_async
#     def serialize_booking(self, booking: Booking):
#         return BookingSerializer(booking).data
