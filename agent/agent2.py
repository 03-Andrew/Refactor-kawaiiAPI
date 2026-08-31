from pathlib import Path
import os
import sys
from langchain_google_genai import ChatGoogleGenerativeAI
from typing import Annotated, Literal
from typing_extensions import TypedDict, List
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import MemorySaver
from dotenv import load_dotenv
from pydantic import BaseModel
import django
from datetime import date, datetime
from collections import Counter
import json
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, AnyMessage

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))
# 2. Point to your Django settings module      
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kawaiiAPI.settings.dev')
# 3. Initialize Django runtime & ORM                                                                      
django.setup()   

from agent.states import BookingState
from agent.nodes import (
    select_and_hold_rooms, search_available_rooms, collect_boat_transfer, 
    collect_customer_info, display_booking_summary, cancel_booking, 
    confirm_booking, book, route_booking_confirmation, route_stage
)


graph = StateGraph(BookingState)

graph.add_node('search_available_rooms', search_available_rooms)
graph.add_node('select_and_hold_rooms', select_and_hold_rooms)
graph.add_node('collect_customer_info', collect_customer_info)
graph.add_node('collect_boat_transfer', collect_boat_transfer)
graph.add_node('confirm_booking', confirm_booking)
graph.add_node('book', book)
# graph.add_node('cancel_booking', cancel_booking)

graph.add_conditional_edges(
    START,
    route_stage,
    {
        'search_available_rooms': 'search_available_rooms',
        'select_and_hold_rooms': 'select_and_hold_rooms',
        'collect_customer_info': 'collect_customer_info',
        'collect_boat_transfer': 'collect_boat_transfer',
        'confirm_booking': 'confirm_booking'
    }
)

graph.add_edge('search_available_rooms', END)
graph.add_edge('select_and_hold_rooms', END)
graph.add_edge("collect_customer_info", END)
graph.add_edge("collect_boat_transfer", END)
graph.add_conditional_edges(
    'confirm_booking',
    route_booking_confirmation,
    {
        'book': 'book',
        'cancel_booking': END,
    }
)
graph.add_edge("book", END)

checkpointer = MemorySaver()
APP = graph.compile(checkpointer=checkpointer)

def run_chatbot():
    import uuid
    import json
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    print("--- Resort Booking Assistant ---")
    print("Type 'exit' to quit.\n")

    while True:
        user_input = input("Message: ").strip()
        if user_input.lower() == "exit":
            print("BYE")
            break
        if not user_input:
            continue

        state_snapshot = APP.get_state(config)

        if state_snapshot.next:
            state = APP.invoke(Command(resume=user_input), config=config)
        else:
            state = APP.invoke(
                {"messages": [HumanMessage(content=user_input)]},
                config=config,
            )

        if state.get("messages") and len(state["messages"]) > 0:
            last_message = state["messages"][-1]
            content = getattr(last_message, "content", "")
            if isinstance(last_message, dict):
                content = last_message.get("content", "")
            print(f"Assistant: {json.dumps(content, indent=4)}\n")

if __name__ == "__main__":
    run_chatbot()

