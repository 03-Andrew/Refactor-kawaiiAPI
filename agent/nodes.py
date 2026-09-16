from pathlib import Path
import os
import sys
from langchain_openai import ChatOpenAI
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
from bookings.services.booking import create_online_booking, lookup_billing
from bookings.exceptions import RedisUnavailable, RoomTypeNotFoundError
from bookings.models import RoomType
from paymongo.views import create_checkout_link

from .utils import release_locks, get_room_type_availability, get_room_types, get_recent_messages, convert_to_24h, handle_common_back_action, display_booking_summary, get_room_names

from agent.states import (
    BookingState, BaseStageInput, DateAndGuestCountInput, SelectedRoomsInput, 
    GuestInfo, AvailBoat, ConfirmBooking, RoomTypeDetails, InitalGreetingState, RoomCacheSchema,
    DateAndGuestCountInputWithUserInfo, IntentClassification, BookingLookUp
)
from datetime import datetime 
from langsmith import traceable

ROOM_CACHE = RoomCacheSchema()

customer_info_input = """
                      Extract the customer's contact details from their input:
                        - first_name: First / given name (e.g. Wilbert)
                        - last_name: Last name / surname (e.g. Smith)
                        - email: Email address (e.g. andrew@gmail.com)
                        - phone_number: Contact / mobile phone number (e.g. 09771203453)
                        
                        If a field is not mentioned in the input, leave it as null/None.
                      """

llm_classifier  = ChatGoogleGenerativeAI(
    model="gemini-3.1-flash-lite",
    temperature=0, 
    max_tokens=None,
    timeout=None,
    max_retries=2,    
)


llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0, 
    max_retries=2,    
)

FORMATTING_PROMPT = """
                    Formatting rules (always follow these):
                    - Separate sections with blank line.
                    - Never output a wall of text — keep each section visually distinct.
                    - Do not use markdown tables; use bullet lists instead.
                    """

@traceable                                                                                                                                                                                   
def classify_intent(state: BookingState):                                                                                                                                                                                   
    """Quickly classifies user intent considering current stage and conversation context."""                                                                                                                                                    
    messages = state.get('messages', [])
    last_message = messages[-1] if messages else ""
    user_input = getattr(last_message, 'content', str(last_message))
    stage = state.get('stage') or 'greet'

    # Get the previous assistant prompt if available for context
    last_bot_prompt = ""
    for msg in reversed(messages[:-1]):
        if isinstance(msg, AIMessage) or (isinstance(msg, dict) and msg.get('role') == 'assistant'):
            last_bot_prompt = getattr(msg, 'content', str(msg))
            break

    classifier = llm.with_structured_output(IntentClassification)                                                                                                                                                           
    result = classifier.invoke([
        {
            "role": "system",
            "content": (
                f"Classify user intent for a resort booking bot.\n"
                f"Stage: '{stage}' | Last bot prompt: '{last_bot_prompt}'\n\n"
                "Categories:\n"
                "- 'book': Booking details, dates, or directly answering the stage prompt (e.g. room name, contact info, yes/no).\n"
                "- 'rag_node': User is ASKING a question (policies, amenities, rules, prices).\n"
                "- 'greet': Pleasantries or hello.\n\n"
                "Rule: Answering the bot prompt is always 'book'. Asking a question is 'rag_node'."
            )
        },
        {"role": "user", "content": user_input}
    ])                                                                                                                                                                                                                  
                                                                                                                                                                                             
    return {"intent": result.intent} 

@traceable
def greet_user(state: BookingState):
    """Initial greeting to the user."""
    print("RUNNING Greet User")
    last_message = state['messages'][-1]
    user_input = getattr(last_message, 'content', last_message.get('content', '') if isinstance(last_message, dict) else str(last_message))
    extractor = llm.with_structured_output(InitalGreetingState)
    result = extractor.invoke([
        {
            "role": "system",
            "content": f"""You are a friendly and helpful resort booking assistant. if the user greets you, greet them back, ask them if they want to book a room"""
        },
        {
            "role": "user",
            "content": user_input
        }
    ])

    # first_name = result.first_name or state.get("first_name")
    # last_name = result.last_name or state.get("last_name")
    # email = result.email or state.get("email")
    # phone_number = result.phone_number or state.get("phone_number")


    return {
        "messages": [{"role": "assistant", "content": result.message}],
        "stage": result.stage,
        "room_types_to_display": getattr(result, "room_types_to_display", []),
    }          

@traceable
def search_available_rooms(state: BookingState):
    """Collects user adult and children count with their desired checkin and checkout dates"""
    print("RUNNING COLLECT_DATES_AND_COUNT")
    last_message = state['messages'][-1]
    extractor = llm.with_structured_output(DateAndGuestCountInputWithUserInfo)
    now = datetime.now()
    result = extractor.invoke([
        {
            "role": "system",
            "content": f"""Collect adult count, children count, checkin date (first date mentoned), checkout date (first date mentoned) and desired_room_type (if the user mentioned a specific room name like 'deluxe room')
            The date today is {now.strftime("%Y-%m-%d")}, use that to calculate relative dates. 
            Check_in and check_out dates are string types with format of (YYYY-MM-DD). If not mentioned just set it to none (0 for the children count)
            validate dates first, checkin should not be after checkout, if so reask dates. If mentioned {customer_info_input}
            """
        }, *get_recent_messages(state=state)
    ])


    check_in = result.check_in or state.get("check_in")
    check_out = result.check_out or state.get("check_out")
    adult_count = result.adult_count or state.get("adult_count")
    children_count = result.children_count if result.children_count is not None else state.get("children_count", 0)
    first_name = result.first_name or state.get("first_name")
    last_name = result.last_name or state.get("last_name")
    email = result.email or state.get("email")
    phone_number = result.phone_number or state.get("phone_number")

    check_in_date = datetime.strptime(check_in, "%Y-%m-%d") if check_in else None
    check_out_date = datetime.strptime(check_out, "%Y-%m-%d") if check_out else None

    state_results = {
        "check_in":check_in,
        "check_out":check_out,                   
        "adult_count": adult_count,
        "children_count": children_count,  
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone_number": phone_number,    
    }

    if check_in_date and check_out_date and (check_in_date > check_out_date):
        msg = f"Dates are invalid, please provide valid dates."
        state_results["messages"] = [AIMessage(content=msg)]
        state_results["stage"] = 'search_available_rooms'
        return state_results

    missing = []
    if not check_in: missing.append("check-in date")
    if not check_out: missing.append("check-out date")
    if not adult_count: missing.append("number of adult guests")


    # If anything is missing, ask for it and STOP (do not call DB)
    if missing:
        msg = f"To check availability, please provide your {', '.join(missing)}."
        state_results["messages"] = [AIMessage(content=msg)]
        state_results["stage"] = 'search_available_rooms'
        return state_results


    rooms = get_room_type_availability(
        check_in=check_in,
        check_out=check_out,
        adult_count=adult_count,
        children_count=children_count
    )

    if not rooms:
        msg = f"Sorry, there are no available rooms between {check_in} and {check_out}."
        state_results["messages"] = [AIMessage(content=msg)]
        state_results["stage"] = 'search_available_rooms'
        return state_results

    if result.desired_room_type:
        desired = result.desired_room_type.lower()
        matched_room = next(
            (r for r in rooms if desired in r["name"].lower() and r["available_rooms"] > 0),
            None     
        )
        if matched_room:
            msg=(                                                                                                                                                                                                         
                    f"**{matched_room['name']} is available!** (₱{matched_room['price']:,.2f} / night)\n\n"                                                                                                                     
                    f"Would you like to **hold** this room for 10 minutes, or add more rooms?"                                                                                                                                  
                )
            state_results["messages"] = [AIMessage(content=msg)]
            state_results["stage"] = 'select_and_hold_rooms'
            state_results["room_type_ids"] = [matched_room["id"]]
            return state_results
        
        else:     
            msg = (                                                                                                                                                                                                         
                f"Sorry, **{result.desired_room_type}** is not available for your selected dates.\n"                                                                                                                        
                f"Here are the rooms that are available:\n"                                                                                                                                                                 
                + "\n".join([f"• **{r['name']}** (₱{r['price']:,.2f})" for r in rooms])                                                                                                                                     
                + "\n\nWhich room would you like to reserve instead?"                                                                                                                                                       
            )
            state_results["messages"] = [AIMessage(content=msg)]
            state_results["stage"] = 'search_available_rooms'
            return state_results
                                                                                                                                                                                                                     

    guest_summary = f"{adult_count} adult{'s' if adult_count > 1 else ''}"
    if children_count:
        guest_summary += f", {children_count} child{'ren' if children_count > 1 else ''}"

    lines = [
        f"Here are the available rooms for **{check_in}** to **{check_out}** ({guest_summary}):\n"
    ]
    for r in rooms:
        line = f"• **{r['name']}** — ₱{r['price']:,.2f} / night (Capacity: {r['good_for']} guests (max extra guest: {r['max_extra_guest']}) | Available: {r['available_rooms']})"
        suggested = r.get("suggested_number_of_rooms_to_book") or 1
        if suggested > 1:
            line += f"\n  - *Recommended: {suggested} rooms to comfortably accommodate your party*"
        lines.append(line)

    lines.append("\nWhich room type would you like to reserve?")
    reply_msg = "\n".join(lines)

    state_results["messages"] = [AIMessage(content=reply_msg)]
    state_results["stage"] = 'select_and_hold_rooms'
    state_results["room_types_to_display"] = [r["id"] for r in rooms]
    return state_results


@traceable
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
            Determine if the user wants to hold/lock/proceed with their selection (e.g. they say 'hold', 'lock', 'proceed', 'yes'). Set wants_to_hold=True in that case.
            If the user wants to add more rooms, set wants_to_hold=False.
            Determine if the user wants to change their selection, modify dates/guest count, or cancel. If so, set action to 'change_room', 'modify_dates_or_guests', or 'cancel' respectively. Otherwise, set action to 'continue'."""
        },
        {
            "role": "user",
            "content": user_input
        }
    ])
    # print(result.action)
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
            "**Current Room Selection:**\n"
            + "".join(formatted_rooms)
            + f"\n**Subtotal per night:** ₱{total_nightly_price:,.2f}"
            "\nWould you like to **add more rooms**, or **hold** these rooms to move to the next step? "
            "*\n(Reply **hold** to lock your rooms for 10 minutes, or specify additional rooms to add)*"
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
            "messages": [AIMessage(content="Redis lock service is currently unavailable. Please try again.")],
            "stage": "select_and_hold_rooms"
        }

    except RoomTypeNotFoundError as exc:
        return {
            "status": "error",
            "error_type": "room_type_not_found",
            "messages": [AIMessage(content=f"Room type not found: {exc}")],
            "stage": "select_and_hold_rooms"
        }

    if not bulk_lock.get('all_held'): 
        return { 
            "status": "unavailable",
            'failures': bulk_lock.get('failures', []),
            "messages": [AIMessage(content="Sorry, some of the selected rooms are no longer available. Please select another room.")],
            "stage": "select_and_hold_rooms"
        }       

    first_name = state.get('first_name')
    last_name = state.get('last_name')
    phone_number = state.get('phone_number')
    email = state.get('email')

    missing = []
    if not first_name: missing.append('first name')
    if not last_name: missing.append('last name')
    if not email: missing.append('email')
    if not phone_number: missing.append('phone number')

    if missing:
        msg = (
            "**Rooms Selected & Held:**"
            + "\n".join(formatted_rooms)
            + f"\n *These rooms are now held for you for 10 minutes.*\n"
            f"Please provide your {', '.join(missing)} to proceed with the booking."
        )

        return {
            "status": "success",                                                                                                                                                            
            "room_type_ids": all_room_type_ids,                                                                                                                                                 
            "holder_id": bulk_lock["holder_id"],        
            "messages": [AIMessage(content=msg)],
            "stage": "collect_customer_info"
        }   

        
    held_msg = (
        "**Rooms Selected & Held:**"
        + "\n".join(formatted_rooms)
        + f"\n *These rooms are now held for you for 10 minutes.*\n"
        "Would you like to avail of boat transfer? If yes, please select a time (6 AM, 8 AM, 10 AM, 12 PM, 3 PM, 5 PM), or reply no."
    )
    return {                                                                                                                                                                            
        "status": "success",                                                                                                                                                            
        "room_type_ids": all_room_type_ids,                                                                                                                                                 
        "holder_id": bulk_lock["holder_id"],                                                                                                                                            
        "messages": [AIMessage(content=held_msg)],
        "stage": "collect_boat_transfer"                                                                                                                                                                            
    }     

@traceable
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
        *get_recent_messages(state, window_size=6)
    ])

    # print(result.action)
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

@traceable
def collect_boat_transfer(state: BookingState):
    print("RUNNING collect_boat_transfer")

    result = llm.with_structured_output(AvailBoat).invoke([
        {
            "role": "system",
            "content": """Determine whether the user wants to avail boat transfer.
            If yes, set avail_boat_transfer=True and extract the boat transfer time. If no, set avail_boat_transfer=False, otherwise leave it None and boat_transfer_time=None. 
            Dont assume time input, if not provided leave blank, if time not in selected timeslots place leave blank and ask the user to input correct time
            Determine if the user wants to change their selection, modify dates/guest count, or cancel. 
            If so, set action to 'change_room', 'modify_dates_or_guests', or 'cancel' respectively. Otherwise, set action to 'continue'."""
        },
        *get_recent_messages(state, window_size=6)
    ])

    if result.action != "continue":
        # print(result.action)
        return handle_common_back_action(state, result)

    avail_boat = result.avail_boat_transfer                                                                                                                                             
    boat_time = convert_to_24h(result.boat_transfer_time) if avail_boat else None 

    fresh_state = {                                                                                                                                                                     
            **state,                                                                                                                                                                        
            "avail_boat_transfer": avail_boat,                                                                                                                                              
            "boat_transfer_time": boat_time,                                                                                                                                                
    }  


    if avail_boat is False:
        summary_message = display_booking_summary(fresh_state)
        return {
            "avail_boat_transfer": False,
            "boat_transfer_time": None,
            "stage": "confirm_booking",
            "messages": [AIMessage(content=summary_message)]
        } 
    elif avail_boat:
        if not boat_time:
            return {
                "avail_boat_transfer": True,
                "head_count": (state.get("adult_count") or 1) + (state.get("children_count") or 0),
                "boat_transfer_time": None,
                "stage": "collect_boat_transfer",
                "messages": [AIMessage(content="Time input might be invalid or empty, here are available times (6 AM, 8 AM, 10 AM, 12 PM, 3 PM, 5 PM)")]
            }
        else:
            summary_message = display_booking_summary(fresh_state)
            return {
                "avail_boat_transfer": True,
                "head_count": (state.get("adult_count") or 1) + (state.get("children_count") or 0),
                "boat_transfer_time": boat_time,
                "stage": "confirm_booking",
                
                "messages": [AIMessage(content=summary_message)]
            }
    else:
        return {
                "stage": "collect_boat_transfer",
                "messages": [AIMessage(content="Please let us know if you would like to avail of the boat transfer (Yes or No). Available times: (6 AM, 8 AM, 10 AM, 12 PM, 3 PM, 5 PM)")]
            }

@traceable
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

    # print(result.action)
    if result.action != "continue":
        return handle_common_back_action(state, result)
    
    return {
        "confirmed": result.confirmed
    }

@traceable
def route_booking_confirmation(state: BookingState):
    print("RUNNING route_booking_confirmation")
    if state.get("confirmed"):
        return "book"
    else:
        return END

@traceable
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
        billing_id = billing.id if billing else None
        booking_objs = booking_result.get("booking", [])
        booking_ids = [b.id for b in booking_objs] if isinstance(booking_objs, list) else getattr(booking_objs, "id", "N/A")

        first_name = customer_data.get("first_name") or "Guest"
        last_name = customer_data.get("last_name") or ""
        checkout_response = create_checkout_link(billing, str(billing_id))
        print(checkout_response)
        check_out_url = checkout_response.get("data", {}).get("attributes", {}).get("checkout_url", "")
        release_locks(state)
        return {
            "status": "booked",
            "billing_id": billing_id,
            "stage": "await_payment",
            "messages": [
                AIMessage(
                    content=(
                        f"**Booking Confirmed!**\n"
                        f"Thank you, {first_name} {last_name}!\n"
                        f"**Billing Ref:** #{billing_id}\n"
                        f"Please complete your payment by tapping the link below\n"
                        f"[{check_out_url}]({check_out_url})\n"
                        f"Once you're done paying, just send me a message and I'll confirm your payment!"
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
                    content=f"We encountered an issue while finalizing your booking: {e}. Please contact our support team or try again."
                )
            ]
        }

@traceable
def await_payment(state: BookingState):
    """Checks if the billing has been paid after the user notifies us."""
    print("RUNNING await_payment")
    from transactions.models import Billing, BillingStatus

    billing_id = state.get("billing_id")
    first_name = state.get("first_name") or "Guest"

    if not billing_id:
        return {
            "messages": [AIMessage(content="I couldn't find your billing record. Please contact our support team.")],
            "stage": "await_payment"
        }

    try:
        billing = Billing.objects.get(id=billing_id)
    except Billing.DoesNotExist:
        return {
            "messages": [AIMessage(content="Billing record not found. Please contact our support team.")],
            "stage": "await_payment"
        }

    paid_statuses = {BillingStatus.BOOKING_PAID}

    if billing.status in paid_statuses:
        return {
            "status": "paid",
            "stage": "greet",
            "messages": [
                AIMessage(
                    content=(
                        f"**Payment Received!**\n"
                        f"Thank you, {first_name}! Your payment has been confirmed.\n"
                        f"**Billing Ref:** #{billing_id}\n"
                        f"We look forward to hosting you at Kawaii Resort!\n"
                        f"If you need anything else, feel free to message us."
                    )
                )
            ]
        }
    else:
        return {
            "stage": "await_payment",
            "messages": [
                AIMessage(
                    content=(
                        f" We haven't received your payment yet, {first_name}.\n"
                        f"Please complete your payment using the link sent earlier. "
                        f"Once done, just send me a message and I'll check again! "
                    )
                )
            ]
        }

@traceable
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

@traceable
def look_up_booking(state: BookingState):
    last_message = state['messages'][-1]
    user_input = getattr(last_message, "content", str(last_message))

    result = llm.with_structured_output(BookingLookUp).invoke([
        {
            "role": "system",
            "content": (
                "Extract the customer's email address and billing reference number "
                "(format: BL-XXXXXX) from the user message for booking lookup."
            )
        },
        {"role": "user", "content": user_input}
    ])

    email = result.email
    billing_reference = result.billing_reference

    missing = []
    if not email: missing.append("email")
    if not billing_reference: missing.append("billing reference number (e.g. BL-ABC123)")

    if missing:
        msg = f"To look up your booking, please provide: {', '.join(missing)}."
        return {
            "messages": [AIMessage(content=msg)],
            "stage": 'look_up'
        }

    billing = lookup_billing(billing_reference=billing_reference, email=email)

    if not billing:
        msg = (
            f"No booking found for billing reference **{billing_reference}** "
            f"with email **{email}**. Please double-check and try again."
        )
        return {
            "messages": [AIMessage(content=msg)],
            "stage": "look_up"
        }

    bookings = billing.bookings.all()

    booking_lines = []
    for i, booking in enumerate(bookings, start=1):
        booking_lines.append(
            f"**Booking {i}** (Ref: `{booking.reference_id}`)\n"
            f"* **Room Type:** {booking.room_type.name if booking.room_type else 'N/A'} "
            f"(Room: {booking.room.room_number if booking.room else 'Not Assigned'})\n"
            f"* **Check-In:** `{booking.check_in}` → **Check-Out:** `{booking.check_out}` "
            f"({booking.number_of_nights} night{'s' if booking.number_of_nights != 1 else ''})\n"
            f"* **Guests:** {booking.adult_count} adult(s), {booking.children_count} child(ren)"
            + (f", {booking.extra_guest} extra" if booking.extra_guest else "") + "\n"
            f"* **Status:** `{booking.status}`\n"
            f"* **Cost:** ₱{booking.total_cost}"
        )

    bookings_section = "\n\n".join(booking_lines) if booking_lines else "_No bookings found under this billing._"

    msg = (
        f"### Reservation Details (Billing Ref: **{billing.billing_reference}**)\n\n"
        f"**Billing Status:** `{billing.status}`\n\n"
        "---\n\n"
        f"{bookings_section}\n\n"
        "---\n"
        f"*Billing created: {billing.created_at.strftime('%Y-%m-%d %H:%M') if billing.created_at else 'N/A'}*"
    )

    return {
        "messages": [AIMessage(content=msg)],
    }