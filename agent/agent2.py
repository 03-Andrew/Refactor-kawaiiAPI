from pathlib import Path
import os
import sys
from langchain_google_genai import ChatGoogleGenerativeAI
from typing import Annotated, Literal
from typing_extensions import TypedDict, List
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode
from dotenv import load_dotenv
from pydantic import BaseModel
import django
from datetime import date

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))
# 2. Point to your Django settings module      
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kawaiiAPI.settings.dev')
# 3. Initialize Django runtime & ORM                                                                      
django.setup()   


from bookings.services.availability import get_room_types_availability, get_room_type_basic_info

class BookingState(TypedDict):
    messages: Annotated[list, add_messages]

    check_in: date | None = None
    check_out: date | None = None
    adult_count: int | None = None
    children_count: int | None = None

    first_name: str | None = None
    last_name: str | None = None


class DateAndGuestCountInput(BaseModel):
    check_in: date
    check_out: date
    adult_cout: int
    children_count: int

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

customer_data_input = llm.with_structured_output(GuestInfo)

graph = StateGraph(BookingState)

def greet_user(state: BookingState):
    """First greet the user"""


@tool
def collect_dates_and_count(state: BookingState):
    """Collects user adult and children count with their desired checkin and checkout dates"""
    last_message = state['messages'][-1]
    date_and_guest_count_input = llm.with_structured_output(DateAndGuestCountInput)

    result = date_and_guest_count_input.invoke([
        {
            "role": "system",
            "content": """Collect adult count, children count, checkin date and checkout date"""
        },
        {
            "role": "user",
            "content": last_message.content
        }
    ])

    state['check_in'] = result['check_in']
    state['check_out'] = result['check_out']
    state['adult_count'] = result['adult_count']
    state['children_count'] = result['children_count']
    return state


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

@tool(description="Retrieve available room types and their availability counts between check_in and check_out dates (YYYY-MM-DD).")
def get_room_type_availability(*, check_in=None, check_out=None, adult_count=None, childdren_count=None, room_type=None) -> list[RoomTypeAvailabilityCount]:
    return [
        {
            "id": rt.id,
            "name": rt.name,
            "price": rt.price,
            "good_for": rt.good_for,
            "available_rooms": rt.available_rooms
        }
        for rt in get_room_type_availability(check_in=check_in, check_out=check_out, room_type=room_type)
    ] 

def hold_room_type_for_booking():
    """Holds room using a redis lock with a 10 minute TTL to give time for users to book and to block any conccurent bookings incase of a shortage of rooms"""

def release_room_type():
    """Releases room type redis lock if user completes booking or decides to go back either change booking dates or head count or if they changed their minds"""

def collect_customer_info():
    """After selecting rooms, users are then asked to type in their information, namely, their names, email, phone number and if they plan to avail boat transfer. 
    If they do avail boat transfer, ask them a list of names (this is optional they can either fill this out in the resort of fill it out now)."""

def upload_booking_return_payment_checkout_link():
    """After filling out their info, call the upload booking and return a link that redirects user to another page to pay"""

def verify_payment():
    """Once payment is complete ask user if they have done the payment"""

def complete_booking():
    """User session is complete, release the locks and show them final details"""



tools = [collect_dates_and_count]

llm_with_tools = llm.bind_tools(tools)

tool_node = ToolNode(tools)

graph.add_node("tool_node", tool_node)

def prompt_node(state: BookingState) -> BookingState:
    new_message = llm_with_tools.invoke(state["messages"])
    return {"messages": [new_message]}

graph.add_node("prompt_node", prompt_node)

def conditional_edge(state: BookingState) -> Literal['tool_node', '__end__']:
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tool_node"
    else:
        return "__end__"
    
graph.add_conditional_edges(
    'prompt_node',
    conditional_edge
)
graph.add_edge("tool_node", "prompt_node")
graph.set_entry_point("prompt_node")

APP = graph.compile()

if __name__ == "__main__":
    while True:
        user_message = input("Message: ")
        if user_message == "exit":
            break

        new_state = APP.invoke({"messages": [user_message]})
        print(new_state["messages"][-1].content[-1]['text'])


