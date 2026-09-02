from rest_framework import serializers
from bookings.serializers import RoomTypeSerializer
class ChatMessageSerializer(serializers.Serializer):
    message = serializers.CharField(
        required=True,
        help_text="The message content from the user."
    )
    thread_id = serializers.CharField(
        required=False,
        default=None,
        allow_null=True,
        allow_blank=True,
        help_text="Optional thread ID to maintain conversation context. If omitted, a new thread will be started."
    )

class ChatMessageResponseSerializer(serializers.Serializer):
    reply = serializers.CharField(
        required=True,
        help_text="The response content from the chatbot."
    )
    thread_id = serializers.CharField(
        required=True,
        help_text="Thread ID maintaining conversation context."
    )
    stage = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="The current stage of the conversation."
    )
    status = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="Booking status (e.g. booked, cancelled, error)."
    )
    booking_details = serializers.DictField(
        required=False,
        allow_null=True,
        help_text="Optional booking details if applicable."
    )
