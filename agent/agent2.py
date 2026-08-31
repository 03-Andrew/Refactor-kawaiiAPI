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


from bookings.services.availability import get_room_types_availability, get_room_type_basic_info, bulk_lock_room_type
from bookings.services.booking import create_online_booking
from bookings.exceptions import RedisUnavailable, RoomTypeNotFoundError
from bookings.models import RoomType
class BookingState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]

    check_in: date | None = None
    check_out: date | None = None
    adult_count: int | None = None
    children_count: int | None = None

    room_type_ids: list[int] = []
    confirmed: bool | None = None

    holder_id: str | None = None

    status: str | None = None
    error_type: str | None = None
    failures: list[str] = []

    first_name: str | None = None
    last_name: str | None = None
    phone_number: str | None = None
    email: str | None = None

    avail_boat_transfer: bool | None = None
    head_count: int | None = None   
    boat_transfer_time: str | None = None



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

class AvailBoat(BaseModel):
    avail_boat_transfer: bool

class BoatTime(BaseModel):
    head_count: int
    boat_transfer_time: str
    # guests: list[str] = []

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
    boat: BoatTime



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
    print("RUNNING COLLECT_DATES_AND_COUNT")
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
    print("RUNNING query_get_room_types")
    rooms = get_room_type_availability(
        check_in=state['check_in'],
        check_out=state['check_out'],
        adult_count=state['adult_count'],
        childdren_count=state['children_count']
    )

    if not rooms:
        message = "No available rooms during these dates"
        return {'messages': [{"role":"assistant", "content": message}]}

    last_message = state['messages'][-1]
    user_content = getattr(last_message, 'content', last_message.get('content', '') if isinstance(last_message, dict) else str(last_message))
    prompt = [
        {
            "role": "system",
            "content": f"""Display the room information to the cusomer using these data {rooms}. If count is less than capacity 
                           (good for) you can reccomend multiple rooms for that single type only if available count allows"""
        },
        {
            "role": "user",
            "content": user_content
        }
    ]
    reply = llm.invoke(prompt)
    return {'messages': [{"role":"assistant", "content": reply.content}]}

def collect_selected_room_type_ids(state: BookingState):
    """Collects selected room type ids from user"""
    print("RUNNING collect_selected_room_type_ids")
    rooms = get_room_type_availability(
        check_in=state['check_in'],
        check_out=state['check_out'],
        adult_count=state['adult_count'],
        childdren_count=state['children_count']
    )
    user_input = interrupt({
        "type":"room_selection"
    })

    selected_room_types = llm.with_structured_output(SelectedRoomsInput)

    result = selected_room_types.invoke([
        {
            "role": "system",
            "content": f"""extract room type ids from the user input and store it in a list here are the room details and ids for reference {rooms}.
                           If a user wants to book multiple rooms of the same type, just appen the same id based on the count the user needs"""
        },
        {
            "role": "user",
            "content": user_input
        }
    ])

    return {
        "room_type_ids": result.room_type_ids
    }

def print_selected_rooms(state: BookingState):
    """Display selected rooms and ask the user to confirm before holding."""
    print("RUNNING print_selected_rooms")
    room_type_ids = state.get("room_type_ids", [])
    print(room_type_ids)

    rooms = list(
        RoomType.objects
        .filter(id__in=set(room_type_ids))
        .values("id", "name", "price", "good_for")
    )

    room_map = {room["id"]: room for room in rooms}

    room_counts = Counter(room_type_ids)

    if not rooms:
        return {
            "message": [ AIMessage(f"I couldn't find the selected room type(s): {room_type_ids}. Please select your room again.")]
        }

    formatted_rooms = [] 
    for room_type_id, quantity in room_counts.items():
        room =  room_map.get(room_type_id)
        if not room:
            continue

        total_price = room['price'] * quantity

        formatted_rooms.append(
            f"{room['name']} × {quantity} "
            f"(₱{room['price']} each, ₱{total_price} total)"
        )

    message = (
        "You've selected:\n\n"
        + "\n".join(f"• {room}" for room in formatted_rooms)
        + "\n\n"
        "Would you like me to hold these rooms for your booking? "
        "Please reply **yes** to confirm or **no** to change your selection."
    )

    return {
        "messages": [
            AIMessage(content=message)
        ]
    }

class ConfirmHold(BaseModel):
    confirmed: bool

def confirm_hold(state: BookingState):
    print("RUNNING confirm_hold")
    user_input = interrupt({
        "type": "confirmation",
        "message": "Would you like me to hold these rooms"
    })

    result = llm.with_structured_output(ConfirmHold).invoke([
        {
            "role": "system",
            "content": """Determine whether the user wants to proceed with
            holding the selected rooms.

            Return:
            - confirmed=True if they want to proceed/book/hold
            - confirmed=False if they want to cancel/change their selection"""
        },
        {
            "role": "user",
            "content": user_input
        }
    ])

    return {
        "confirmed": result.confirmed
    }

def route_confirm(state: BookingState):
    if state['confirmed']:
        return "hold_room"
    else:
        return "hell_na"

def oh_yeah(state: BookingState):

    return {"messages":[AIMessage(content=f"Oh YEAH {state}")]}

def hell_na(state: BookingState):
    return {"messages":[ AIMessage(content="HELL NA")]}
    
def hold_room(state: BookingState):
    """Room selection to lock specified rooms"""
    print("RUNNING hold_room")
    rooms = [{"check_in": state["check_in"], "check_out": state["check_out"], "room_type_id": room_id} for room_id in state['room_type_ids']]
    try: 
        bulk_lock = bulk_lock_room_type(rooms)



    except RedisUnavailable:
        return {
            "status": "error",
            "error_type": "redis_unavailable",
            "messages": [ AIMessage(content="Redis service broken bruh")]
        }

    except RoomTypeNotFoundError as exc:
        return {
            "status": "error",
            "error_type": "room_type_not_found",
            "messages": [AIMessage(content=f"Bruh a room type is not found {exc}")]
        }

    if not bulk_lock['all_held']: 
        return { 
            "status": "unavailable",
            'failures': bulk_lock.failures,
            "messages": [AIMessage(content=f"Some rooms are no longer available")]
        }

    return {
        'status': "success",
        'holder_id': bulk_lock['holder_id'],
        'messages': [                                                                                                                                                                   
            AIMessage(content="Your rooms have been held for 10 minutes! Please provide your first name, last name, phone number, and email:")                                          
        ]      
    }

def collect_customer_info(state: BookingState):
    """After selecting rooms, users are then asked to type in their information (first name, last name, email, phone number)"""
    print("RUNNING COLLECT_CUSTOMER_INFO")
    user_input = interrupt({"type": "confirmation"})

    guest_info = llm.with_structured_output(GuestInfo)

    result = guest_info.invoke([
        {
            "role": "system",
            "content": """Extract the user's details: first name, last name, email, and phone number."""
        },
        {
            "role": "user",
            "content": user_input
        }
    ])
    return {
        "first_name": result.first_name,
        "last_name": result.last_name,
        "email": result.email,
        "phone_number": result.phone_number,
        "messages": [                                                                                                                                                                   
            AIMessage(content="Would you like to avail boat transfer?")                                          
        ]      
    }

def will_avail_boat(state: BookingState):
    print("RUNNING will_avail_boat")
    user_input = interrupt({
        "type": "confirmation",
    })

    result = llm.with_structured_output(AvailBoat).invoke([
        {
            "role": "system",
            "content": """Determine whether the user wants to avail boat transfer, return a boolean"""
        },
        {
            "role": "user",
            "content": user_input
        }
    ])
    updates = {"avail_boat_transfer": result.avail_boat_transfer}                                                                                                                       
    if result.avail_boat_transfer:                                                                                                                                                      
        updates["messages"] = [                                                                                                                                                         
            AIMessage(content="Please select a boat transfer time: 6 AM, 8 AM, 10 AM, 12 PM, 3 PM, or 5 PM.")                                                                           
        ]                                                                                                                                                                               
    return updates         
 

def parse_boat_time_to_24h(time_str: str | None) -> str:
    """Parse time string like '8 AM', '3 PM', '12:00 PM', '15:00' to HH:MM 24-hour format."""
    if not time_str:
        return "10:00"

    clean_str = time_str.strip().upper()

    # Direct format matching
    for fmt in ("%I:%M %p", "%I %p", "%I:%M%p", "%I%p", "%H:%M:%S", "%H:%M"):
        try:
            parsed = datetime.strptime(clean_str, fmt)
            return parsed.strftime("%H:%M")
        except ValueError:
            pass

    time_map = {
        "6 AM": "06:00",
        "8 AM": "08:00",
        "10 AM": "10:00",
        "12 PM": "12:00",
        "3 PM": "15:00",
        "5 PM": "17:00",
        "6:00 AM": "06:00",
        "8:00 AM": "08:00",
        "10:00 AM": "10:00",
        "12:00 PM": "12:00",
        "3:00 PM": "15:00",
        "5:00 PM": "17:00",
    }
    return time_map.get(clean_str, "10:00")


def boat_time_input(state: BookingState):
    """Ask if user wants to avail boat transfer and display available times."""
    print("RUNNING boat_time_input")
    user_input = interrupt({
        "type": "confirmation"
    })  

    boat_time = llm.with_structured_output(BoatTime)

    result = boat_time.invoke([
        {
            "role": "system",
            "content": """
            Determine which boat transfer time the user selected.
            Convert the time to 24-hour HH:MM format:
            6 AM -> "06:00"
            8 AM -> "08:00"
            10 AM -> "10:00"
            12 PM -> "12:00"
            3 PM -> "15:00"
            5 PM -> "17:00"
            """
        },
        {
            "role": "user",
            "content": user_input
        }
    ])

    formatted_time = parse_boat_time_to_24h(result.boat_transfer_time)

    return {
        "head_count": state["adult_count"] + state["children_count"],
        "boat_transfer_time": formatted_time
    }

def route_will_avail(state: BookingState):
    if state.get("avail_boat_transfer"):
        return "boat_time_input"
    else: 
        return "booking_details"


def booking_details(state: BookingState):
    """Display comprehensive booking details before final booking confirmation."""
    print("RUNNING booking_details")
    room_type_ids = state.get("room_type_ids", [])

    rooms = list(
        RoomType.objects
        .filter(id__in=set(room_type_ids))
        .values("id", "name", "price", "good_for")
    )

    room_map = {room["id"]: room for room in rooms}
    room_counts = Counter(room_type_ids)

    # Calculate number of nights
    nights = 1
    try:
        ci = state.get("check_in")
        co = state.get("check_out")
        if isinstance(ci, str):
            ci = datetime.strptime(ci, "%Y-%m-%d").date()
        if isinstance(co, str):
            co = datetime.strptime(co, "%Y-%m-%d").date()
        if ci and co:
            nights = max((co - ci).days, 1)
    except Exception:
        nights = 1

    formatted_rooms = []
    total_room_cost = 0
    for room_type_id, quantity in room_counts.items():
        room = room_map.get(room_type_id)
        if not room:
            continue

        price_per_night = float(room["price"])
        subtotal = price_per_night * quantity * nights
        total_room_cost += subtotal

        formatted_rooms.append(
            f"• **{room['name']}** × {quantity} (₱{price_per_night:,.2f}/night × {nights} night{'s' if nights > 1 else ''} = ₱{subtotal:,.2f})"
        )

    # Boat transfer info
    if state.get("avail_boat_transfer"):
        boat_time = state.get("boat_transfer_time") or "Not selected"
        head_count = state.get("head_count") or ((state.get("adult_count") or 0) + (state.get("children_count") or 0))
        boat_info = f"Yes (Time: {boat_time}, Head Count: {head_count})"
    else:
        boat_info = "No"

    customer_name = f"{state.get('first_name', '')} {state.get('last_name', '')}".strip() or "N/A"
    phone = state.get("phone_number") or "N/A"
    email = state.get("email") or "N/A"
    check_in = str(state.get("check_in") or "N/A")
    check_out = str(state.get("check_out") or "N/A")
    adults = state.get("adult_count", 0)
    children = state.get("children_count", 0)

    summary_lines = [
        "📋 **Booking Summary & Details**\n",
        "**Guest Information:**",
        f"• Name: {customer_name}",
        f"• Email: {email}",
        f"• Phone: {phone}\n",
        "**Stay Information:**",
        f"• Check-in: {check_in}",
        f"• Check-out: {check_out} ({nights} night{'s' if nights > 1 else ''})",
        f"• Guests: {adults} Adult(s), {children} Child(ren)\n",
        "**Rooms Reserved:**",
        *(formatted_rooms if formatted_rooms else [f"• Room IDs: {room_type_ids}"]),
        f"\n**Boat Transfer:** {boat_info}",
        f"**Estimated Total:** ₱{total_room_cost:,.2f}\n",
        "Would you like to confirm and finalize this booking? Please reply **yes** to proceed or **no** to cancel."
    ]

    message = "\n".join(summary_lines)

    return {
        "messages": [
            AIMessage(content=message)
        ]
    }

class ConfirmBooking(BaseModel):
    confirmed: bool

def confirm_booking(state: BookingState):
    """HITL step: Waits for the user's final confirmation on the booking details."""
    print("RUNNING confirm_booking")
    user_input = interrupt({
        "type": "booking_confirmation",
        "message": "Would you like to confirm and finalize this booking?"
    })

    result = llm.with_structured_output(ConfirmBooking).invoke([
        {
            "role": "system",
            "content": """Determine whether the user confirms and wants to proceed with the booking.
            Return:
            - confirmed=True if they agree/confirm/say yes
            - confirmed=False if they decline/cancel/say no"""
        },
        {
            "role": "user",
            "content": user_input
        }
    ])

    return {
        "confirmed": result.confirmed
    }

def route_booking_confirmation(state: BookingState):
    print("RUNNING route_booking_confirmation")
    if state.get("confirmed"):
        return "book"
    else:
        return "cancel_booking"

def book(state: BookingState):
    """Final booking step that formats the payload and calls create_online_booking."""
    print("RUNNING book")

    # 1. Customer payload
    customer_data = {
        "first_name": state.get("first_name", ""),
        "last_name": state.get("last_name", ""),
        "contact_number": state.get("phone_number") or state.get("contact_number", ""),
        "email": state.get("email", ""),
    }

    # 2. Rooms payload
    room_type_ids = state.get("room_type_ids", [])
    num_rooms = max(len(room_type_ids), 1)
    total_adults = state.get("adult_count") or 1
    total_children = state.get("children_count") or 0
    adults_per_room = max(1, total_adults // num_rooms)

    rooms_data = []
    adults_assigned = 0
    children_assigned = 0

    for i, rt_id in enumerate(room_type_ids):
        if i == num_rooms - 1:
            r_adults = max(1, total_adults - adults_assigned)
            r_children = max(0, total_children - children_assigned)
        else:
            r_adults = adults_per_room
            r_children = total_children // num_rooms
            adults_assigned += r_adults
            children_assigned += r_children

        rooms_data.append({
            "room_type": rt_id,
            "check_in": str(state.get("check_in")),
            "check_out": str(state.get("check_out")),
            "adult_count": r_adults,
            "children_count": r_children,
            "extra_guest": 0,
            "room_number": 0,
        })

    # 3. Boat payload
    if state.get("avail_boat_transfer"):
        full_name = f"{state.get('first_name', '')} {state.get('last_name', '')}".strip()
        boat_time_val = parse_boat_time_to_24h(state.get("boat_transfer_time"))
        boat_data = {
            "head_count": state.get("head_count") or (total_adults + total_children),
            "time": boat_time_val,
            "guests": [full_name] if full_name else ["Lead Guest"],
        }
    else:
        boat_data = None

    holder_id = state.get("holder_id")

    try:
        booking_result = create_online_booking(
            customer=customer_data,
            rooms=rooms_data,
            boat_details=boat_data,
            holder_id=holder_id,
        )

        billing = booking_result.get("billing")
        billing_id = billing.id if billing else "N/A"
        booking_objs = booking_result.get("booking", [])
        booking_ids = [b.id for b in booking_objs] if isinstance(booking_objs, list) else getattr(booking_objs, "id", "N/A")

        first_name = customer_data.get("first_name") or "Guest"
        last_name = customer_data.get("last_name") or ""

        return {
            "status": "booked",
            "messages": [
                AIMessage(
                    content=(
                        f"🎉 **Booking Confirmed!**\n\n"
                        f"Thank you, {first_name} {last_name}!\n"
                        f"• **Billing Reference ID:** `#{billing_id}`\n"
                        f"• **Booking ID(s):** {booking_ids}\n"
                        f"• **Hold Reference:** `{holder_id}`\n\n"
                        "Please proceed to the secure checkout page to complete your payment:\n"
                        f"🔗 [Proceed to Payment Checkout](https://kawaii-resort.example.com/checkout?bill_id={billing_id})\n\n"
                        "We look forward to hosting you!"
                    )
                )
            ]
        }
    except Exception as e:
        print(f"Error creating online booking: {e}")
        return {
            "status": "error",
            "error_type": str(e),
            "messages": [
                AIMessage(
                    content=f"⚠️ We encountered an issue while finalizing your booking: {e}. Please contact our support team or try again."
                )
            ]
        }

def cancel_booking(state: BookingState):
    print("RUNNING cancel_booking")
    return {
        "status": "cancelled",
        "messages": [
            AIMessage(
                content="Your booking has been cancelled. Please let us know if you'd like to start over or make changes to your stay."
            )
        ]
    }

def route_room_selection(state: BookingState):
    print("RUNNING route_room_selection")
    if state['status'] == "success":
        print("SUCCESS")
        return "success"
    if state['status'] == 'unavailable':
        print("BRUH")
        return "unavailable"
    return "error"

graph = StateGraph(BookingState)

graph.add_node('collect_initial_details', collect_dates_and_count)
graph.add_node('query_get_room_types', query_get_room_types)
graph.add_node('collect_selected_room_type_ids', collect_selected_room_type_ids)
graph.add_node('print_selected_rooms', print_selected_rooms)
graph.add_node('confirm_hold', confirm_hold)
graph.add_node('oh_yeah', oh_yeah)
graph.add_node('hold_room', hold_room)
graph.add_node('hell_na', hell_na)
graph.add_node('collect_customer_info', collect_customer_info)
graph.add_node('will_avail_boat', will_avail_boat)
graph.add_node('boat_time_input', boat_time_input)
graph.add_node('booking_details', booking_details)
graph.add_node('confirm_booking', confirm_booking)
graph.add_node('book', book)
graph.add_node('cancel_booking', cancel_booking)


graph.add_edge(START, 'collect_initial_details')
graph.add_edge('collect_initial_details', 'query_get_room_types')
graph.add_edge('query_get_room_types', 'collect_selected_room_type_ids')
graph.add_edge('collect_selected_room_type_ids', 'print_selected_rooms')
graph.add_edge('print_selected_rooms', 'confirm_hold')
graph.add_conditional_edges(
    'confirm_hold',
    route_confirm,
    {
        "hold_room": "hold_room",
        'hell_na': "hell_na"
    }
)

graph.add_edge("hell_na", "collect_selected_room_type_ids")
graph.add_conditional_edges(
    'hold_room',
    route_room_selection,
    {
        'success': "collect_customer_info",
        'unavailable': END,
        'error': END, 
    },
)

graph.add_edge("collect_customer_info", "will_avail_boat")
graph.add_conditional_edges(
    'will_avail_boat',
    route_will_avail,
    {
        'boat_time_input': 'boat_time_input',
        'booking_details': 'booking_details'
    }
)
graph.add_edge("boat_time_input", "booking_details")
graph.add_edge("booking_details", "confirm_booking")
graph.add_conditional_edges(
    'confirm_booking',
    route_booking_confirmation,
    {
        'book': 'book',
        'cancel_booking': 'cancel_booking',
    }
)
graph.add_edge("book", END)
graph.add_edge("cancel_booking", END)

checkpointer = MemorySaver()
APP = graph.compile(checkpointer=checkpointer)


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

def release_room_type():
    """Releases room type redis lock if user completes booking or decides to go back either change booking dates or head count or if they changed their minds"""


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

        # print(state["extras"])

if __name__ == "__main__":
    run_chatbot()

