from django.urls import path
from agent.views import AgentChatAPIView

urlpatterns = [
    path('api/agent/chat/', AgentChatAPIView.as_view(), name='agent_chat'),
]
