from dotenv import load_dotenv
from typing import Annotated, Literal
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field
from typing_extensions import TypedDict
from datetime import date
from bookings.services.availability import get_room_types_availability
import getpass
import os

load_dotenv()

if "GOOGLE_API_KEY" not in os.environ:
    os.environ["GOOGLE_API_KEY"] = getpass.getpass("Enter your Google AI API key: ")

llm = init_chat_model("google_genai:gemini-2.5-flash")


class InitialInput(BaseModel):
    check_in: date = Field(description="Check in date of user stay")
    check_out: date = Field(description="Check out date of user stay")
    adult_count: int = Field(description="Number of adults")
    childrein_counr: int = Field(description="Number of children")

class State(TypedDict):
    messages: Annotated[list, add_messages]


graph_builder = StateGraph(State)

def get_initial_booking_details(state: State):
    last_message = state['messages'][-1]
    classifier_llm = llm.with_structured_output(InitialInput)

    messages = [
        {
            "role": "system",
            "content": """ You are a resort bookin ageny:
            collect check in and check out dates and adult and children count for user wanting to book a room
            """
        },
        {
            "role": "user",
            "content": last_message.content
        }
    ]
    result = classifier_llm.invoke(messages)
    return {"messages": result}


def router(state: State):  
    message_type = state.get("message_type", "logical")
    if message_type == "emotional":
        return {"next": "therapist"}
    elif message_type == "logical":
        return {"next": "logical"}
    return {"next": "booking"}

def logical_agent(state: State):
    last_message = state["messages"][-1]

    messages = [
        {"role": "system",
         "content": """You are a purely logical assistant. Focus only on facts and information.
            Provide clear, concise answers based on logic and evidence.
            Do not address emotions or provide emotional support.
            Be direct and straightforward in your responses."""
         },
        {
            "role": "user",
            "content": last_message.content
        }
    ]
    reply = llm.invoke(messages)
    return {"messages": [{"role": "assistant", "content": reply.content}]}


graph_builder.add_node("booking", get_initial_booking_details)
graph_builder.add_edge(START, "booking")
graph_builder.add_edge("booking", END)
graph = graph_builder.compile( )


def run_chatbot():
    state={"messages": [], "message_type": None}
    while True:
        user_input = input("Message: ")
        if user_input == "exit":
            print("BYE")
            break

        state["messages"] = state.get("messages", []) + [
            {"role": "user", "content": user_input}
        ]

        state = graph.invoke(state)

        if state.get("messages") and len(state["messages"]) > 0:
            last_message = state["messages"][-1]
            print(f"Assistant: {last_message.content[0]["text"]}")

if __name__ == "__main__":
    run_chatbot()

