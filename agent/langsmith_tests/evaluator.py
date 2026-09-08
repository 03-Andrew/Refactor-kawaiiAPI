from datetime import date
from langsmith import evaluate, Client
from dotenv import load_dotenv
from pathlib import Path
import sys
import os
import django
from uuid import uuid4
from langchain_core.messages import HumanMessage

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))
from django.apps import apps
if not apps.ready:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kawaiiAPI.settings.dev')
    django.setup()   

from agent.agent2 import APP

load_dotenv()
client = Client()
def multi_turn_target(inputs: dict) -> dict:
    """
    Sequentially feeds all user turns into the graph under the same thread_id
    to simulate a real multi-turn conversation and accumulate state.
    """
    config = {"configurable": {"thread_id": str(uuid4())}}
    final_state = {}
    for msg in inputs.get("messages", []):
        final_state = APP.invoke(
            {"messages": [HumanMessage(content=msg)]},
            config=config
    )
            
    return final_state

def single_turn_target(inputs: dict) -> dict:
    """Invokes graph for single-turn extraction tests."""
    config = {"configurable": {"thread_id": str(uuid4())}}
    return APP.invoke(
        {"messages": [{"role": "user", "content": inputs["messages"][0]["content"]}]},
        config=config
    )


def evaluate_multi_turn_state(outputs: dict, reference_outputs: dict) -> dict:
    """
    Compares the graph's final accumulated state against the reference outputs.
    Normalizes dates and string casing for robust validation.
    """
    fields_to_check = [
        "check_in",
        "check_out",
        "adult_count",
        "children_count",
        "room_type_ids",
        "first_name",
        "last_name",
        "email",
        "phone_number",
        "avail_boat_transfer",
        "boat_transfer_time",
        "stage",
    ]

    matched_fields = 0
    total_fields = 0
    comments = []

    for field in fields_to_check:
        if field not in reference_outputs:
            continue
        
        total_fields += 1
        ref = reference_outputs[field]
        pred = outputs.get(field)

        # Normalize date types to string format (YYYY-MM-DD)
        if isinstance(pred, date):
            pred = pred.strftime("%Y-%m-%d")

        # Case-insensitive string matching for names/emails
        if isinstance(ref, str) and isinstance(pred, str):
            is_match = (pred.strip().lower() == ref.strip().lower())
        else:
            is_match = (pred == ref)

        if is_match:
            matched_fields += 1
        else:
            comments.append(f"❌ {field}: expected '{ref}', got '{pred}'")

    score = (matched_fields / total_fields) if total_fields > 0 else 0.0

    return {
        "key": "multi_turn_state_match",
        "score": score,
        "comment": "; ".join(comments) if comments else "✅ All state fields matched perfectly!"
    }

if __name__ == "__main__":
    multi_turn_dataset = "Customer multi-turn booking v1"
    print(f"Running evaluation on '{multi_turn_dataset}'...")
    evaluate(
        multi_turn_target,
        data=multi_turn_dataset,
        evaluators=[evaluate_multi_turn_state],
        experiment_prefix="Multi-Turn Conversation State Test"
    )


