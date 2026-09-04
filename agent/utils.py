from pathlib import Path
import os
import sys
from dotenv import load_dotenv
import django
from datetime import date, datetime
from langchain_core.messages import AIMessage
from collections import Counter

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
from paymongo.views import create_checkout_link

from agent.states import (
    BookingState, BaseStageInput, DateAndGuestCountInput, SelectedRoomsInput, 
    GuestInfo, AvailBoat, ConfirmBooking, RoomTypeDetails, InitalGreetingState, RoomCacheSchema
)


from bookings.models import RoomType

ROOM_CACHE = RoomCacheSchema()

def get_room_types() -> list[RoomTypeDetails]:
    current_time = datetime.now()
    if ROOM_CACHE.data is not None and ROOM_CACHE.last_updated is not None:
        time_diff = (current_time - ROOM_CACHE.last_updated).total_seconds()
        if time_diff < 3600:  # 1 hour in seconds
            return ROOM_CACHE.data
    print("Fetching room types from the database...")
    ROOM_CACHE.data = [
        {
            "id": rt.id,
            "name": rt.name,
            "price": rt.price,
            "description": rt.description,
            "good_for": rt.good_for,
            "inclusions":[inc.inclusion for inc in rt.inclusions.all()]
        }
        for rt in get_room_type_basic_info()
    ]
    ROOM_CACHE.last_updated = datetime.now()
    return ROOM_CACHE.data

def convert_to_24h(time_str: str | None) -> str | None:
    if not time_str or not isinstance(time_str, str):
        return None
    time_str = time_str.strip().upper()
    formats = [
        "%H:%M",
        "%H:%M:%S",
        "%I:%M %p",
        "%I %p",
        "%I:%M%p",
        "%I%p",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(time_str, fmt).strftime("%H:%M")
        except ValueError:
            continue
    return None


def get_recent_messages(state: BookingState, window_size: int = 6) -> list:                                                                                                   
    """Return the last N messages to maintain natural conversational context while capping token usage."""                                                                    
    messages = state.get("messages") or []                                                                                                                                    
    return messages[-window_size:]     

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

def get_room_type_availability(*, check_in=None, check_out=None, adult_count=None, children_count=None, room_type=None):
    """Retrieve available room types and their availability counts between check_in and check_out dates (YYYY-MM-DD)."""
    guest_count = adult_count+children_count
    return [
        {
            "id": rt['room_type'].id,
            "name": rt['room_type'].name,
            "price": rt['room_type'].price,
            "good_for": rt['room_type'].good_for,
            "max_extra_guest": rt['room_type'].max_extra_guest,
            "available_rooms": rt['available_rooms'],
            "suggested_number_of_rooms_to_book": rt["suggested_number_of_rooms_to_book"],
            "should_add_extra_guest": rt["should_add_extra_guest"],
            "pair_with_other_rooms": rt["pair_with_other_rooms"],
            "can_accommodate_group": rt["can_accommodate_group"]
        }
        for rt in get_room_types_availability(check_in=check_in, check_out=check_out, room_type=room_type, guest_count=guest_count)
    ] 

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
                f"**{r['name']}** (ID: `{r['id']}`) - ₱{float(r['price']):,.2f}/night, good for {r['good_for']} guests ({r['available_rooms']} left)"
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
                f"You've chosen to change your room selection to **{matched_room['name']}**. Here are the available room types for your selected dates:\n{room_options}\nPlease specify the room you'd like to reserve. If you want to add more rooms, you can specify them as well."
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
                f"I've released your previously held room. Here are the available room types for your selected dates:\n{room_options}\nPlease specify the room you'd like to reserve. If you want to add more rooms, you can specify them as well."
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
            f"You've chosen to modify your booking details. {changes_str}\n"
            f"- **Stay:** {state.get('check_in')} to {state.get('check_out')}\n"
            f"- **Guests:** {guests_str}\n\n"
            f"**Available Room Types:**\n{room_list_str}\n\n"
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
            f"  • {room['name']} × {quantity}  —  ₱{price_per_night:,.2f}/night × {nights} night{'s' if nights > 1 else ''} = ₱{subtotal:,.2f}"
        )

    # Boat transfer info
    if state.get("avail_boat_transfer"):
        boat_time = state.get("boat_transfer_time") or "Not selected"
        head_count = state.get("head_count") or ((state.get("adult_count") or 0) + (state.get("children_count") or 0))
        boat_info = f"✅ Yes  |  Time: {boat_time}  |  Pax: {head_count}"
    else:
        boat_info = "❌ No"

    customer_name = f"{state.get('first_name', '')} {state.get('last_name', '')}".strip() or "N/A"
    phone = state.get("phone_number") or "N/A"
    email = state.get("email") or "N/A"
    check_in = str(state.get("check_in") or "N/A")
    check_out = str(state.get("check_out") or "N/A")
    adults = state.get("adult_count", 0)
    children = state.get("children_count", 0)
    nights_label = f"{nights} night{'s' if nights > 1 else ''}"

    rooms_block = "\n".join(formatted_rooms) if formatted_rooms else f"  • Room IDs: {room_type_ids}"

    message = (
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏨  **BOOKING SUMMARY**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Guest Information**\n"
        f"  • Name:   {customer_name}\n"
        f"  • Email:  {email}\n"
        f"  • Phone:  {phone}\n"
        f"📅 **Stay Details**\n"
        f"  • Check-in:   {check_in}\n"
        f"  • Check-out:  {check_out}  ({nights_label})\n"
        f"  • Guests:     {adults} Adult(s),  {children} Child(ren)\n"
        f"🛏️ **Rooms Reserved**\n"
        f"{rooms_block}\n"
        f"⛵ **Boat Transfer**\n"
        f"  {boat_info}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 **Estimated Total:  ₱{total_room_cost:,.2f}**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Please reply **yes** to confirm and finalize your booking, or **no** to cancel."
    )

    return message
