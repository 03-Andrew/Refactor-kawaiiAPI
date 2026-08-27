from pathlib import Path
import os
import sys
from langchain_google_genai import ChatGoogleGenerativeAI
from typing import Annotated, Literal
from typing_extensions import TypedDict
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode
from dotenv import load_dotenv
import django

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))
# 2. Point to your Django settings module      
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kawaiiAPI.settings.dev')
# 3. Initialize Django runtime & ORM                                                                      
django.setup()   
from bookings.services.availability import get_room_types_availability


llm  = ChatGoogleGenerativeAI(
    model="gemini-3.7-flash",
    temperature=1.0,  # Gemini 3.0+ defaults to 1.0
    max_tokens=None,
    timeout=None,
    max_retries=2,
)

class State(TypedDict):
    messages: Annotated[list, add_messages]

graph = StateGraph(State)

@tool
def get_room_types(*, check_in="2026-10-10", check_out="2026-10-12", room_type=None):
    """Retrieve available room types and their availability counts between check_in and check_out dates (YYYY-MM-DD)."""
    rooms = get_room_types_availability(check_in=check_in, check_out=check_out, room_type=room_type)
    return rooms
    
tools = [get_room_types]

llm_with_tools = llm.bind_tools(tools)

tool_node = ToolNode(tools)

graph.add_node("tool_node", tool_node)

def prompt_node(state: State) -> State:
    new_message = llm_with_tools.invoke(state["messages"])
    return {"messages": [new_message]}

graph.add_node("prompt_node", prompt_node)

def conditional_edge(state: State) -> Literal['tool_node', '__end__']:
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

new_state = APP.invoke({"messages": ["Show me room types"]})

print(new_state["messages"][-1].content[-1]['text'])