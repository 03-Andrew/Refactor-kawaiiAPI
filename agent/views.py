import uuid
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from drf_spectacular.utils import extend_schema

from agent.agent2 import APP
from agent.serializers import ChatMessageSerializer, ChatMessageResponseSerializer
from agent.nodes import get_room_types
from django.http import StreamingHttpResponse
import json

class AgentChatAPIView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Agent Chat API"],
        request=ChatMessageSerializer,
        responses={200: ChatMessageResponseSerializer},
        description="Interact with the LangGraph AI Booking Assistant."
    )
    def post(self, request):
        serializer = ChatMessageSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user_message = serializer.validated_data["message"].strip()
        thread_id = serializer.validated_data.get("thread_id") or str(uuid.uuid4())

        config = {"configurable": {"thread_id": str(thread_id)}}

        try:
            state_snapshot = APP.get_state(config)

            if state_snapshot.next:
                state = APP.invoke(Command(resume=user_message), config=config)
            else:
                state = APP.invoke(
                    {"messages": [HumanMessage(content=user_message)]},
                    config=config,
                )

            reply = "I'm sorry, I couldn't process your request."
            if state.get("messages") and len(state["messages"]) > 0:
                last_message = state["messages"][-1]
                content = getattr(last_message, "content", "")
                if isinstance(content, list):
                    content = content[0].get("text", "")
                reply = content

            # print(state)  # Debugging: Print the state after invoking with resume


            booking_details = {
                "check_in": str(state.get("check_in")) if state.get("check_in") else None,
                "check_out": str(state.get("check_out")) if state.get("check_out") else None,
                "adult_count": state.get("adult_count"),
                "children_count": state.get("children_count"),
                "room_type_ids": state.get("room_type_ids", []),
                "avail_boat_transfer": state.get("avail_boat_transfer"),
                "boat_transfer_time": state.get("boat_transfer_time"),
            }



            response_data = {
                "reply": reply,
                "thread_id": str(thread_id),
                "stage": state.get("stage"),
                "status": state.get("status"),
                "booking_details": booking_details,
            }
            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {
                    "error": f"Agent processing failed: {str(e)}",
                    "thread_id": str(thread_id)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )



