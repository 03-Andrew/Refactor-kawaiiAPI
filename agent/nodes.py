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
from bookings.services.lock import release_holder_locks
from bookings.services.booking import create_online_booking
from bookings.exceptions import RedisUnavailable, RoomTypeNotFoundError
from bookings.models import RoomType
from paymongo.views import create_checkout_link

from agent.states import (
    BookingState, BaseStageInput, DateAndGuestCountInput, SelectedRoomsInput, 
    GuestInfo, AvailBoat, ConfirmBooking, RoomTypeDetails
)
from datetime import datetime

def convert_to_24h(time_str: str) -> str:
    try:
        return datetime.strptime(time_str, "%I:%M %p").strftime("%H:%M")
    except ValueError:
        return datetime.strptime(time_str, "%I %p").strftime("%H:%M")

llm  = ChatGoogleGenerativeAI(
    model="gemini-3.1-flash-lite",
    temperature=1.0,  # Gemini 3.0+ defaults to 1.0
    max_tokens=None,
    timeout=None,
    max_retries=2,    
)


def release_locks(state: BookingState):
    """Release holder locks"""
    holder_id = state.get("holder_id")
    check_in = state.get("check_in")
    check_out = state.get("check_out")
    rooms_to_release = [{"check_in": check_in, "check_out": check_out, "room_type_id": room_id} for room_id in state.get("room_type_ids", [])] 

    try:
        release_holder_locks(rooms_to_release, holder_id)
    except Exception as e:
        print(f"Error occurred while releasing locks: {e}")

def handle_common_back_action(state: BookingState, result: BaseStageInput):
    if result.action == "change_room":
        if state.get("holder_id"):
            release_locks(state)

        available_rooms = get_room_type_availability(
            check_in=state.get("check_in"),
            check_out=state.get("check_out"),
            adult_count=state.get("adult_count"),
            children_count=state.get("children_count")
        )
        
        valid_rooms = [r for r in available_rooms if r.get("available_rooms", 0) > 0]
        if valid_rooms:
            room_options = "\n".join([
                f"• **{r['name']}** (ID: `{r['id']}`) - ₱{float(r['price']):,.2f}/night, good for {r['good_for']} guests ({r['available_rooms']} left)"
                for r in valid_rooms
            ])
        else:
            room_options = "⚠️ No rooms are currently available for these dates."

        # Check if user already mentioned a specific room (e.g. 'family room')
        new_room_name = getattr(result, "new_room_type", None)
        matched_room = None
        if new_room_name:
            new_room_clean = new_room_name.strip().lower()
            for r in valid_rooms:
                if new_room_clean in r["name"].lower():
                    matched_room = r
                    break

        if matched_room:
            msg = (
                f"You've chosen to change your room selection to **{matched_room['name']}**. Here are the available room types for your selected dates:\n\n{room_options}. Please specify the room you'd like to reserve. If you want to add more rooms, you can specify them as well."
            )
            return {
                "holder_id": None,
                "room_type_ids": [matched_room["id"]],
                "stage": "select_and_hold_rooms",
                "messages": [
                    AIMessage(content=msg)
                ]
            }
        
        else:
            msg = (
                f"I've released your previously held room.\n\nHere are the available room types for your selected dates: {room_options} Please specify the room you'd like to reserve. If you want to add more rooms, you can specify them as well."
            )
            return {
                "holder_id": None,
                "room_type_ids": [],
                "stage": "select_and_hold_rooms",
                "messages": [
                    AIMessage(content=msg)
                ]
            }

    elif result.action == "modify_dates_or_guests":
        if state.get("holder_id"):
            release_locks(state)

        changes = []

        if result.new_check_in is not None:
            state["check_in"] = result.new_check_in
            changes.append(f"check-in date to {result.new_check_in}")
        if result.new_check_out is not None:
            state["check_out"] = result.new_check_out
            changes.append(f"check-out date to {result.new_check_out}")
        if result.new_adult_count is not None:
            state["adult_count"] = result.new_adult_count
            changes.append(f"adult count to {result.new_adult_count}")
        if result.new_children_count is not None:
            state["children_count"] = result.new_children_count
            changes.append(f"children count to {result.new_children_count}")

        available_rooms = get_room_type_availability(
            check_in=state.get("check_in"),
            check_out=state.get("check_out"),
            adult_count=state.get("adult_count"),
            children_count=state.get("children_count")
        )

        room_list_str = "\n".join([                                                                                                                                                  
            f"• **{r['name']}** (ID: `{r['id']}`) - ₱{float(r['price']):,.2f}/night, good for {r['good_for']} guests ({r['available_rooms']} available)"                             
            for r in available_rooms                                                                                                                                                 
        ]) 
        changes_str = f"Updated {', '.join(changes)}." if changes else "Dates updated."                                                                                              
        guests_str = f"{state.get('adult_count', 0)} adults, {state.get('children_count', 0)} children"   

        msg = (
            f"You've chosen to modify your booking details.\n"
            f"• **Status:** {changes_str}\n"
            f"• **Stay:** {state.get('check_in')} to {state.get('check_out')}\n"
            f"• **Guests:** {guests_str}\n\n"
            f"**Available Room Types:**\n"
            f"{room_list_str}\n\n"
            f"Which room would you like to select? (Reply with room name or ID)"
        )
        return {
            "holder_id": None,
            "room_type_ids": [],
            "check_in": state.get("check_in"),
            "check_out": state.get("check_out"),
            "adult_count": state.get("adult_count"),
            "children_count": state.get("children_count"),
            "stage": "search_available_rooms",
            "messages": [AIMessage(content=msg)]
        }

    elif result.action == "cancel":
        if state.get("holder_id"):
            release_locks(state)

        return {
            "holder_id": None,
            "room_type_ids": [],
            "status": "cancelled",
            "stage": "cancelled",
            "messages": [
                AIMessage(content="Your booking process has been canceled. If you'd like to start over, please provide your check-in and check-out dates along with the number of guests.")
            ]
        }

    else:
        return None
    
def get_room_type_availability(*, check_in=None, check_out=None, adult_count=None, children_count=None, room_type=None):
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


def search_available_rooms(state: BookingState):
    """Collects user adult and children count with their desired checkin and checkout dates"""
    print("RUNNING COLLECT_DATES_AND_COUNT")
    last_message = state['messages'][-1]
    extractor = llm.with_structured_output(DateAndGuestCountInput)
    now = datetime.now()
    result = extractor.invoke([
        {
            "role": "system",
            "content": f"""Collect adult count, children count, checkin date and checkout date. 
            The date today is {now.strftime("%A")}: {now}, use that to calculate relative dates (e.g. 'tomorrow' or 'next Friday'). 
            Check_in and check_out dates are string types with format of (YYYY-MM-DD). If a value is not mentioned just set it to none or 0 for the children count"""
        }, *state["messages"]
    ])

    check_in = result.check_in or state.get("check_in")
    check_out = result.check_out or state.get("check_out")
    adult_count = result.adult_count or state.get("adult_count")
    children_count = result.children_count if result.children_count is not None else state.get("children_count", 0)

    missing = []
    if not check_in: missing.append("check-in date")
    if not check_out: missing.append("check-out date")
    if not adult_count: missing.append("number of adult guests")


    # If anything is missing, ask for it and STOP (do not call DB)
    if missing:
        msg = f"To check availability, please provide your {', '.join(missing)}."
        return {
            "check_in": check_in,
            "check_out": check_out,
            "adult_count": adult_count,
            "children_count": children_count,
            "messages": [{"role": "assistant", "content": msg}],
            "stage": 'search_available_rooms'
        }


    rooms = get_room_type_availability(
        check_in=check_in,
        check_out=check_out,
        adult_count=adult_count,
        children_count=children_count
    )

    if not rooms:
        msg = f"Sorry, there are no available rooms between {check_in} and {check_out}."
        return {
            "check_in": check_in,
            "check_out": check_out,
            "adult_count": adult_count,
            "children_count": children_count,
            "messages": [{"role": "assistant", "content": msg}],
            "stage": 'search_available_rooms'

        }

    last_message = state['messages'][-1]
    user_content = getattr(last_message, 'content', last_message.get('content', '') if isinstance(last_message, dict) else str(last_message))
    prompt = [
        {
            "role": "system",
            "content": f"""Display the room information to the cusomer using these data {rooms}. If count is less than capacity 
                           (good for), recommend multiple rooms for that single type only if available count allows
                           Ask which room type they would like to reserve."""
        },
        {
            "role": "user",
            "content": user_content
        }
    ]
    reply = llm.invoke(prompt)
    return {
        "check_in": check_in,
        "check_out": check_out,
        "adult_count": adult_count,
        "children_count": children_count,
        "messages": [{"role": "assistant", "content": reply.content}],
        "stage": 'select_and_hold_rooms'
    }

def select_and_hold_rooms(state: BookingState):
    """Allows user to select/add rooms and confirms before applying the 10-minute Redis lock."""
    print("RUNNING select_and_hold_rooms")
    rooms = get_room_type_availability(
        check_in=state['check_in'],
        check_out=state['check_out'],
        adult_count=state['adult_count'],
        children_count=state['children_count']
    )
    last_message = state['messages'][-1]
    user_input = getattr(last_message, "content", str(last_message))

    existing_room_type_ids = state.get("room_type_ids") or []

    selected_parser = llm.with_structured_output(SelectedRoomsInput)       
    result = selected_parser.invoke([
        {
            "role": "system",
            "content": f"""Analyze the user's input based on available rooms: {rooms}.
            Extract any room type IDs the user wants to select or add. If they want multiple rooms of the same type, repeat the ID.
            Determine if the user wants to hold/lock/proceed with their selection (e.g. they say 'hold', 'lock', 'proceed', 'yes', 'done', 'continue', 'that's all', 'next'). Set wants_to_hold=True in that case.
            If the user wants to add more rooms, set wants_to_hold=False.
            Determine if the user wants to change their selection, modify dates/guest count, or cancel. If so, set action to 'change_room', 'modify_dates_or_guests', or 'cancel' respectively. Otherwise, set action to 'continue'."""
        },
        {
            "role": "user",
            "content": user_input
        }
    ])
    print(result.action)
    if result.action != "continue":
        return handle_common_back_action(state, result)
    
    new_ids = result.room_type_ids or []
    wants_to_hold = result.wants_to_hold

    # Combine existing selection with newly selected rooms
    if new_ids:
        all_room_type_ids = existing_room_type_ids + new_ids
    else:
        all_room_type_ids = existing_room_type_ids

    if not all_room_type_ids:                                                                                                                                                               
        return {                                                                                                                                                                        
            "status": "error",                                                                                                                                                          
            "messages": [                                                                                                                                                               
                AIMessage(content="I couldn't identify the rooms you selected. Please specify the room name or ID you would like to reserve.")                                                              
            ],
            "stage": "select_and_hold_rooms"                                                                                                                                                                          
        }

    # Fetch room details from DB for display
    rooms_db = list(                                                                                                                                                                    
        RoomType.objects.filter(id__in=set(all_room_type_ids)).values("id", "name", "price")                                                                                                
    )                                                                                                                                                                                   
    room_map = {r["id"]: r for r in rooms_db}                                                                                                                                           
    room_counts = Counter(all_room_type_ids)                                                                                                                                                
                                                                                                                                                                                        
    formatted_rooms = []                                                                                                                                                                
    total_nightly_price = 0                                                                                                                                                             
    for rt_id, qty in room_counts.items():                                                                                                                                              
        room = room_map.get(rt_id)                                                                                                                                                      
        if room:                                                                                                                                                                        
            subtotal = float(room["price"]) * qty                                                                                                                                       
            total_nightly_price += subtotal                                                                                                                                             
            formatted_rooms.append(f"• **{room['name']}** × {qty} (₱{room['price']:,.2f} each)")

    # If the user has NOT confirmed to hold yet, ask if they want to add more or hold
    if not wants_to_hold:
        selection_msg = (
            "📋 **Current Room Selection:**\n\n"
            + "\n".join(formatted_rooms)
            + f"\n\n**Subtotal per night:** ₱{total_nightly_price:,.2f}\n\n"
            "Would you like to **add more rooms**, or **hold** these rooms to move to the next step?\n"
            "*(Reply **hold** to lock your rooms for 10 minutes, or specify additional rooms to add)*"
        )
        return {
            "room_type_ids": all_room_type_ids,
            "messages": [AIMessage(content=selection_msg)],
            "stage": "select_and_hold_rooms"
        }

    # User confirmed to hold -> Apply Redis lock
    rooms_to_lock = [
        {"check_in": state["check_in"], "check_out": state["check_out"], "room_type_id": room_id} 
        for room_id in all_room_type_ids
    ]
    try: 
        bulk_lock = bulk_lock_room_type(rooms_to_lock)

    except RedisUnavailable:
        return {
            "status": "error",
            "error_type": "redis_unavailable",
            "messages": [AIMessage(content="⚠️ Redis lock service is currently unavailable. Please try again.")],
            "stage": "select_and_hold_rooms"
        }

    except RoomTypeNotFoundError as exc:
        return {
            "status": "error",
            "error_type": "room_type_not_found",
            "messages": [AIMessage(content=f"⚠️ Room type not found: {exc}")],
            "stage": "select_and_hold_rooms"
        }

    if not bulk_lock.get('all_held'): 
        return { 
            "status": "unavailable",
            'failures': bulk_lock.get('failures', []),
            "messages": [AIMessage(content="⚠️ Sorry, some of the selected rooms are no longer available. Please select another room.")],
            "stage": "select_and_hold_rooms"
        }       

    held_msg = (                                                                                                                                                                     
        "🔒 **Rooms Selected & Held:**\n\n"                                                                                                                                             
        + "\n".join(formatted_rooms)                                                                                                                                                    
        + f"\n\n⏳ *These rooms are now held for you for 10 minutes.*\n\n"                                                                                                              
        "Please provide your **first name, last name, email, and phone number** to proceed with the reservation."                                                                       
    )  
    return {                                                                                                                                                                            
        "status": "success",                                                                                                                                                            
        "room_type_ids": all_room_type_ids,                                                                                                                                                 
        "holder_id": bulk_lock["holder_id"],                                                                                                                                            
        "messages": [AIMessage(content=held_msg)],
        "stage": "collect_customer_info"                                                                                                                                                                            
    }     

def collect_customer_info(state: BookingState):
    """After selecting rooms, users are asked to provide their contact information."""
    print("RUNNING COLLECT_CUSTOMER_INFO")
    guest_info = llm.with_structured_output(GuestInfo)

    last_message = state['messages'][-1]
    user_input = getattr(last_message, "content", str(last_message))

    result = guest_info.invoke([
        {
            "role": "system",
            "content": """Extract the customer's contact details from their input:
            - first_name: First / given name (e.g. Wilbert)
            - last_name: Last name / surname (e.g. Smith)
            - email: Email address (e.g. andrew@gmail.com)
            - phone_number: Contact / mobile phone number (e.g. 09771203453)
            
            If a field is not mentioned in the input, leave it as null/None.
            
            If a user says they want to change their contact info, extract the new details and ignore the old ones. If a field is not mentioned in that case, leave it as null/None.
            Determine if the user wants to change their contact info, modify dates/guest count, or cancel. If so, 
            set action to 'change_room', 'modify_dates_or_guests', or 'cancel' respectively. Otherwise, set action to 'continue'."""
        },
        {
            "role": "user",
            "content": user_input
        }
    ])

    print(result.action)
    if result.action != "continue":
        return handle_common_back_action(state, result)

    first_name = result.first_name or state.get('first_name')
    last_name = result.last_name or state.get('last_name')
    email = result.email or state.get('email')
    phone_number = result.phone_number or state.get('phone_number')

    missing = []
    if not first_name: missing.append('first name')
    if not last_name: missing.append('last name')
    if not email: missing.append('email')
    if not phone_number: missing.append('phone number')

    if missing:
        msg = f"Please provide your {', '.join(missing)} to proceed with the booking."
        return {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone_number": phone_number,
            "messages": [AIMessage(content=msg)],
            "stage": "collect_customer_info"
        }

    return {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone_number": phone_number,
        "messages": [                                                                                                                                                                   
            AIMessage(content="Would you like to avail of boat transfer? If yes, please select a time (6 AM, 8 AM, 10 AM, 12 PM, 3 PM, 5 PM), or reply no.")                                          
        ],
        "stage": "collect_boat_transfer"
    }

def collect_boat_transfer(state: BookingState):
    print("RUNNING collect_boat_transfer")
    # last_message = state['messages'][-1]
    # user_input = getattr(last_message, "content", str(last_message))

    result = llm.with_structured_output(AvailBoat).invoke([
        {
            "role": "system",
            "content": """Determine whether the user wants to avail boat transfer.
            If yes, set avail_boat_transfer=True and extract the boat transfer time.
            If no, set avail_boat_transfer=False and boat_transfer_time=None. 
            Dont assume time input, if not provided leave blank, if time not in selected timeslots place leave blank and ask the user to input correct time
            Determine if the user wants to change their selection, modify dates/guest count, or cancel. 
            If so, set action to 'change_room', 'modify_dates_or_guests', or 'cancel' respectively. Otherwise, set action to 'continue'."""
        },
        *state['messages']
    ])

    if result.action != "continue":
        print(result.action)
        return handle_common_back_action(state, result)

    avail_boat = result.avail_boat_transfer                                                                                                                                             
    boat_time = convert_to_24h(result.boat_transfer_time) if avail_boat else None 

    fresh_state = {                                                                                                                                                                     
            **state,                                                                                                                                                                        
            "avail_boat_transfer": avail_boat,                                                                                                                                              
            "boat_transfer_time": boat_time,                                                                                                                                                
    }  


    if not avail_boat:
        summary_message = display_booking_summary(fresh_state)
        return {
            "avail_boat_transfer": False,
            "boat_transfer_time": None,
            "stage": "confirm_booking",
            "messages": [AIMessage(content=summary_message)]
        } 

    if not boat_time:
        return {
            "avail_boat_transfer": True,
            "head_count": (state.get("adult_count") or 1) + (state.get("children_count") or 0),
            "boat_transfer_time": None,
            "stage": "collect_boat_transfer",
            "messages": [AIMessage(content="Time input might be invalid or empty, here are available times (6 AM, 8 AM, 10 AM, 12 PM, 3 PM, 5 PM)")]
        }

    summary_message = display_booking_summary(fresh_state)
    return {
        "avail_boat_transfer": True,
        "head_count": (state.get("adult_count") or 1) + (state.get("children_count") or 0),
        "boat_transfer_time": boat_time,
        "stage": "confirm_booking",
        "messages": [AIMessage(content=summary_message)]
    }



def display_booking_summary(state: BookingState):
    """Display comprehensive booking details before final booking confirmation."""
    print("RUNNING display_booking_summary")
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

    return message
    

def confirm_booking(state: BookingState):
    """HITL step: Waits for user confirmation on the booking details."""
    print("RUNNING confirm_booking")
    last_message = state['messages'][-1]
    user_input = getattr(last_message, "content", str(last_message))

    result = llm.with_structured_output(ConfirmBooking).invoke([
        {
            "role": "system",
            "content": """Determine whether the user confirms and wants to proceed with the booking.
            Return:
            - confirmed=True if they agree/confirm/say yes
            - confirmed=False if they decline/cancel/say no
            Determine if the user wants to change their selection, modify dates/guest count, or cancel.
            If so, set action to 'change_room', 'modify_dates_or_guests', or 'cancel' respectively. Otherwise, set action to 'continue'."""
        },
        {
            "role": "user",
            "content": user_input
        }
    ])

    print(result.action)
    if result.action != "continue":
        return handle_common_back_action(state, result)
    
    return {
        "confirmed": result.confirmed
    }

def route_booking_confirmation(state: BookingState):
    print("RUNNING route_booking_confirmation")
    if state.get("confirmed"):
        return "book"
    else:
        return END

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
        boat_time_val = convert_to_24h(state.get("boat_transfer_time"))
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
        check_out_url = create_checkout_link(billing, "agent booking for " + first_name + " " + last_name)
        release_locks(state)
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
                        f"🔗 [Proceed to Payment Checkout]({check_out_url})\n\n"
                        "We look forward to hosting you!"
                    )
                )
            ]
        }
    except Exception as e:
        print(f"Error creating online booking: {e}")
        release_locks(state)
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
    release_locks(state)
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


def route_stage(state: BookingState):
    stage = state.get('stage') or 'search_available_rooms'                                                                                                                              
                                                                                                                                                                                        
    if stage in [                                                                                                                                                                       
        'search_available_rooms',                                                                                                                                                       
        'select_and_hold_rooms',                                                                                                                                                        
        'collect_customer_info',                                                                                                                                                        
        'collect_boat_transfer',                                                                                                                                                        
        'confirm_booking',                                                                                                                                                              
    ]:                                                                                                                                                                                  
        return stage                                                                                                                                                                    
                                                                                                                                                                                        
    return END  