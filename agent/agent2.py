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
from langgraph.prebuilt import ToolNode
from dotenv import load_dotenv
from pydantic import BaseModel
import django
from datetime import date, datetime


from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, AnyMessage

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))
# 2. Point to your Django settings module      
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kawaiiAPI.settings.dev')
# 3. Initialize Django runtime & ORM                                                                      
django.setup()   


from bookings.services.availability import get_room_types_availability, get_room_type_basic_info, bulk_lock_room_type
from bookings.exceptions import RedisUnavailable, RoomTypeNotFoundError
class BookingState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]

    check_in: date | None = None
    check_out: date | None = None
    adult_count: int | None = None
    children_count: int | None = None

    room_type_ids: list[int] = []
    holder_id: str | None = None

    status: str | None = None
    error_type: str | None = None
    failures: list[str] = []


class DateAndGuestCountInput(BaseModel):
    check_in: str
    check_out: str
    adult_count: int
    children_count: int

class SelectedRoomsInput(BaseModel):
    room_type_ids: list[int]

class GuestInfo(BaseModel):
    first_name: str
    last_name: str
    phone_number: str
    email: str
    avail_boat: bool = False

class BoatAvailed(BaseModel):
    head_count: int
    time: str
    guests: list[str]

class RoomTypeDetails(BaseModel):
    id: int
    name: str
    price: float
    description: str | None = None
    good_for: int | None = None
    inclusions: list[str] = []

class RoomTypeAvailabilityCount(BaseModel):
    id: int 
    name: str
    price: float
    good_for: int
    available_rooms: int

class RoomTypeLock(BaseModel):
    room_type_id: int
    check_in: date
    check_out: date

class RoomTypeSelection(RoomTypeLock):
    adult_count: int
    children_count: int
    extra_guest: int

class RoomTypeHolderLock(BaseModel):
    held: bool
    holder_id: str
    expires_in: int
    rooms: list[RoomTypeLock]


class ReleaseRoomTypeHolderLock(BaseModel):
    released: bool

class OnlineBookingPayload(BaseModel):
    customer: GuestInfo
    rooms: list[RoomTypeSelection]
    boat: BoatAvailed



llm  = ChatGoogleGenerativeAI(
    model="gemini-3.1-flash-lite",
    temperature=1.0,  # Gemini 3.0+ defaults to 1.0
    max_tokens=None,
    timeout=None,
    max_retries=2,    
)

def get_room_type_availability(*, check_in=None, check_out=None, adult_count=None, childdren_count=None, room_type=None):
    """Retrieve available room types and their availability counts between check_in and check_out dates (YYYY-MM-DD)."""
    return [
        {
            "id": rt['room_type'].id,
            "name": rt['room_type'].name,
            "price": rt['room_type'].price,
            "good_for": rt['room_type'].good_for,
            "available_rooms": rt['available_rooms']
        }
        for rt in get_room_types_availability(check_in=check_in, check_out=check_out, room_type=room_type)
    ] 

def collect_dates_and_count(state: BookingState):
    """Collects user adult and children count with their desired checkin and checkout dates"""
    last_message = state['messages'][-1]
    date_and_guest_count_input = llm.with_structured_output(DateAndGuestCountInput)
    now = datetime.now()
    result = date_and_guest_count_input.invoke([
        {
            "role": "system",
            "content": f"""Collect adult count, children count, checkin date and checkout date. 
            The date today is {now.strftime("%A")}: {now}, use that to calculate dates if user
            inputed incomplete dates. Check_in and check_out dates are string types with format of (YYYY-MM-DD)"""
        },
        {
            "role": "user",
            "content": last_message.content
        }
    ])

    return {
        "check_in": result.check_in,
        "check_out": result.check_out,
        "adult_count": result.adult_count,
        "children_count": result.children_count
    }

def query_get_room_types(state: BookingState):
    rooms = get_room_type_availability(
        check_in=state['check_in'],
        check_out=state['check_out'],
        adult_count=state['adult_count'],
        childdren_count=state['children_count']
    )

    if not rooms:
        message = "No available rooms during these dates"
        return {'messages': [{"role":"assistant", "content": message}]}

    last_message = state['messages'][-1].content
    prompt = [
        {
            "role": "system",
            "content": f"""Display the room information to the cusomer using these data {rooms}"""
        },
        {
            "role": "user",
            "content": last_message
        }
    ]
    reply = llm.invoke(prompt)
    return {'messages': [{"role":"assistant", "content": reply.content}]}

def collect_selected_room_type_ids(state: BookingState):
    """Collects selected room type ids from user"""
    last_message = state['messages'][-1]
    selected_room_types = llm.with_structured_output(SelectedRoomsInput)

    result = selected_room_types.invoke([
        {
            "role": "system",
            "content": "extract room type ids from the user input and store it in a list"
        },
        {
            "role": "user",
            "content": last_message.content
        }
    ])

    return {
        "room_type_ids": result.room_type_ids
    }

    

def select_and_hold_room(state: BookingState):
    """Room selection to lock specified rooms"""
    try: 
        bulk_lock = bulk_lock_room_type(state['room_type_ids'])

    except RedisUnavailable:
        return {
            "status": "error",
            "error_type": "redis_unavailable",
            "messages": [{ AIMessage(content="Redis service broken bruh")}]
        }

    except RoomTypeNotFoundError as exc:
        return {
            "status": "error",
            "error_type": "room_type_not_found",
            "messages": [{AIMessage(content=f"Bruh a room type is not found {exc}")}]
        }

    if not bulk_lock.all_held: 
        return { 
            "status": "unavailable",
            'failures': bulk_lock.failures,
            "messages": [{AIMessage(content=f"Some rooms are no longer available")}]
        }

    return {
        'status': "success",
        'holder_id': bulk_lock.holder_id,
    }


def collect_customer_info(state: BookingState):
    """After selecting rooms, users are then asked to type in their information, namely, their names, email, phone number and if they plan to avail boat transfer. 
    If they do avail boat transfer, ask them a list of names (this is optional they can either fill this out in the resort of fill it out now)."""

def human_check(state: BookingState):
    ...

def upload_booking_return_payment_checkout_link():
    """After filling out their info, call the upload booking and return a link that redirects user to another page to pay"""

def route_room_selection(state: BookingState):
    if state['success']:
        return "success"
    if state['unavailable']:
        return "unavailable"
    return "error"


graph = StateGraph(BookingState)

graph.add_node('collect_initial_details', collect_dates_and_count)
graph.add_node('query_get_room_types', query_get_room_types)
graph.add_node('select_room_type', select_and_hold_room)
graph.add_node('guest_detail_input', collect_customer_info)
# graph.add_node('HITL_check', human_check)
# graph.add_node('book', upload_booking_return_payment_checkout_link)



graph.add_edge(START, 'collect_initial_details')
graph.add_edge('collect_initial_details', 'query_get_room_types')
graph.add_edge('query_get_room_types', 'select_room_type')
graph.add_conditional_edges(
    'select_room_type',
    route_room_selection,
    {
        'success': "guest_detail_input",
        'unavailable': END,
        'error': END, 
    },
)
graph.add_edge('guest_detail_input',END)
# graph.add_edge('HITL_check', 'book')
# graph.add_edge('book', END)

APP = graph.compile()


@tool(description="Retrieve room types and their details")
def get_room_types() -> list[RoomTypeDetails]:
    return [
        {
            "id":rt.id,
            "name":rt.name,
            "price":rt.price,
            "description":rt.description,
            "good_for":rt.good_for,
            "inclusions":[inc.inclusion for inc in rt.inclusions.all()]
        }
        for rt in get_room_type_basic_info()
    ]

def hold_room_type_for_booking():
    """Holds room using a redis lock with a 10 minute TTL to give time for users to book and to block any conccurent bookings incase of a shortage of rooms"""

def release_room_type():
    """Releases room type redis lock if user completes booking or decides to go back either change booking dates or head count or if they changed their minds"""

def verify_payment():
    """Once payment is complete ask user if they have done the payment"""

def complete_booking():
    """User session is complete, release the locks and show them final details"""




def run_chatbot():
    state={"messages": []}
    while True:
        user_input = input("Message: ")
        if user_input == "exit":
            print("BYE")
            break

        state["messages"] = state.get("messages", []) + [
            {"role": "user", "content": user_input}
        ]

        state = APP.invoke(state)

        print(state)

        if state.get("messages") and len(state["messages"]) > 0:
            last_message = state["messages"][-1]
            print(f"Assistant: {last_message.content[0]["text"]}")


if __name__ == "__main__":
    run_chatbot()

