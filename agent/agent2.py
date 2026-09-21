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
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
import uuid

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))
from django.apps import apps
if not apps.ready:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kawaiiAPI.settings.dev')
    django.setup()   

from agent.states import BookingState
from agent.nodes import (
    select_and_hold_rooms, search_available_rooms, collect_boat_transfer, 
    collect_customer_info, greet_user, cancel_booking,
    confirm_booking, book, route_booking_confirmation, await_payment, classify_intent, look_up_booking
)

from agent.rag.agent import rag_node

def route_room_selection(state: BookingState):
    print("RUNNING route_room_selection")
    if state['status'] == "success":
        print("SUCCESS")
        return "success"
    if state['status'] == 'unavailable':
        print("BRUH")
        return "unavailable"
    return "error"

def route_stage(state: BookingState):
    stage = state.get('stage') or 'greet'

    if stage == 'greet':                                                                                                                                                                                                    
        return 'classify_intent'             
                                                                                                                                                        
    if stage in [
        'search_available_rooms',                                                                                                                                                       
        'select_and_hold_rooms',                                                                                                                                                        
        'collect_customer_info',                                                                                                                                                        
        'collect_boat_transfer',                                                                                                                                                        
        'confirm_booking',
        'await_payment',
    ]:                                                                                                                                                                                  
        return stage                                                                                                                                                                    
                                                                                                                                                                                        
    return END  

def route_greet(state: BookingState):
    """After greet_user runs, chain directly into search_available_rooms if the user already provided booking intent."""
    stage = state.get('stage') or 'greet'
    if stage == 'search_available_rooms':
        return 'search_available_rooms'
    return END

def route_classified_intent(state: BookingState):
    intent = state.get("intent")
    if intent == "rag_node": return "rag_node"
    if intent == "look_up": return "look_up"
    if intent == "book" and state.get("stage") in (None, "greet"):
        return "search_available_rooms"

    return state.get("stage") or "greet"                                                                                                                                                                                                          


graph = StateGraph(BookingState)

graph.add_node('classify_intent', classify_intent)
graph.add_node('look_up', look_up_booking)
graph.add_node("rag_node", rag_node)
graph.add_node('greet', greet_user)
graph.add_node('search_available_rooms', search_available_rooms)
graph.add_node('select_and_hold_rooms', select_and_hold_rooms)
graph.add_node('collect_customer_info', collect_customer_info)
graph.add_node('collect_boat_transfer', collect_boat_transfer)
graph.add_node('confirm_booking', confirm_booking)
graph.add_node('book', book)
graph.add_node('cancel_booking', cancel_booking)
graph.add_node('await_payment', await_payment)

graph.add_edge(START, 'classify_intent')
graph.add_conditional_edges(
    'classify_intent',
    route_classified_intent,
    {
        'rag_node': 'rag_node',
        'greet': 'greet',                                                                                                                                                                       
        'search_available_rooms': 'search_available_rooms',
        'select_and_hold_rooms': 'select_and_hold_rooms',
        'collect_customer_info': 'collect_customer_info',
        'collect_boat_transfer': 'collect_boat_transfer',
        'confirm_booking': 'confirm_booking',
        'await_payment': 'await_payment',
        'look_up': 'look_up',
    }
)
graph.add_conditional_edges(
    'greet',
    route_greet,
    {
        'search_available_rooms': 'search_available_rooms',
        END: END
    }
)
graph.add_edge('rag_node', END)
graph.add_edge('greet', END)
graph.add_edge('search_available_rooms', END)
graph.add_edge('look_up', END)
graph.add_edge('select_and_hold_rooms', END)
graph.add_edge("collect_customer_info", END)
graph.add_edge("collect_boat_transfer", END)
graph.add_conditional_edges(
    'confirm_booking',
    route_booking_confirmation,
    {
        'book': 'book',
        'cancel_booking': 'cancel_booking',
    }
)
graph.add_edge("cancel_booking", END)
graph.add_edge("book", END)
graph.add_edge("await_payment", END)

checkpointer = MemorySaver()
APP = graph.compile(checkpointer=checkpointer)

# for testing only
def run_chatbot():
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    print("--- Resort Booking Assistant ---")
    print("Type 'exit' to quit.")

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
            if isinstance(content, list):
                print("last_message is a list")
                content = content[0].get("text", "")

            print(f"Assistant: {content}")

if __name__ == "__main__":
    run_chatbot()

