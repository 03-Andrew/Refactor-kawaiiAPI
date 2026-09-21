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
from pydantic import BaseModel, Field
import django
from datetime import date, datetime
from collections import Counter
import json
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, AnyMessage
from langchain_core.documents import Document

class BookingState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    intent: Literal["book", "greet", "look_up", "rag_node"] = None
    rag_answer: str
    
    stage: Literal["greet", "search_available_rooms", "select_and_hold_rooms", "collect_customer_info", "collect_boat_transfer", "confirm_booking", "await_payment", "look_up"] = "greet"
    billing_id: int | None = None
    check_in: date | None = None
    check_out: date | None = None
    adult_count: int | None = None
    children_count: int | None = None
    extra_guest_count: int | None = None

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

    room_types_to_display: list[int] = []

class IntentClassification(BaseModel):                                                                                                                                                                                      
    intent: Literal["book", "greet", "look_up", "rag_node", ""] = Field(                                                                                                                                                               
    description=(                                                                                                                                                                                                       
        "'book' if user wants to reserve, check dates/availability, or provided dates/guests; "                                                                                                                         
        "'rag_node' if user is asking about policies or any FaQ; "                                                                                                                            
        "'greet' if user is just saying hello or asking general assistance."  
        "'look_up' if user wants to view their existing booking"                                                                                                                                          
            )                                                                                                                                                                                                                   
        )    

class BaseStageInput(BaseModel):
    action: Literal["continue", "change_room", "modify_dates_or_guests", "cancel"] = "continue"
    new_check_in: str | None = Field(default=None, description="Updated check-in date in YYYY-MM-DD format")
    new_check_out: str | None = Field(default=None, description="Updated check-out date in YYYY-MM-DD format")
    new_adult_count: int | None = Field(default=None, description="Updated number of adults")
    new_children_count: int | None = Field(default=None, description="Updated number of children")
    new_room_type: str | None = Field(default=None, description="Room name or room type the user wants to switch to")

class RoomTypeDetails(BaseModel):
    id: int | None = None
    name: str | None = None
    price: float | None = None
    description: str | None = None
    good_for: int | None = None
    inclusions: list[str] = []

class RoomCacheSchema(BaseModel):
    data: list[RoomTypeDetails] | None = None
    last_updated: datetime | None = None

class InitalGreetingState(BaseStageInput):
    stage: Literal["greet", "search_available_rooms"] = "greet"
    message: str | None = Field(default=None, description="Message to the user after greeting, structure it with new lines, and bold important information using markdown syntax")
    # room_types_to_display: list[int] = Field(default=[], description="List of available room type IDs")
    # first_name: str | None = Field(default=None, description="Guest first name")
    # last_name: str | None = Field(default=None, description="Guest last name")
    # phone_number: str | None = Field(default=None, description="Guest phone / mobile number")
    # email: str | None = Field(default=None, description="Guest email address")

class DateAndGuestCountInput(BaseStageInput):
    check_in: str | None = None
    check_out: str | None = None
    adult_count: int | None = None
    children_count: int | None = None
    desired_room_type: str | None = Field(
        default=None,
        description="Match the user's requested room to the official room name (e.g. if they say 'delux', resolve to 'Deluxe'). Set None if no room mentioned or if it does not match any known room."
    )
    

class DateAndGuestCountInputWithUserInfo(DateAndGuestCountInput):
    first_name: str | None = Field(default=None, description="Guest first name")
    last_name: str | None = Field(default=None, description="Guest last name")
    phone_number: str | None = Field(default=None, description="Guest phone / mobile number")
    email: str | None = Field(default=None, description="Guest email address")

class SelectedRoomsInput(BaseStageInput):
    room_type_ids: list[int] = []
    wants_to_hold: bool = False


class GuestInfo(BaseStageInput):
    first_name: str | None = Field(default=None, description="Guest first name")
    last_name: str | None = Field(default=None, description="Guest last name")
    phone_number: str | None = Field(default=None, description="Guest phone / mobile number")
    email: str | None = Field(default=None, description="Guest email address")


class AvailBoat(BaseStageInput):
    avail_boat_transfer: bool | None = None
    boat_transfer_time: str | None = None


class BoatTime(BaseModel):
    head_count: int | None = None
    boat_transfer_time: str | None = None




class ConfirmBooking(BaseStageInput):
    confirmed: bool = False

class BookingLookUp(BaseModel):
    email: str | None = None
    billing_reference: str | None = None