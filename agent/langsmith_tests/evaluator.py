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
from agent.utils import release_locks

load_dotenv()
client = Client()

def multi_turn_target(inputs: dict) -> dict:
    """
    Sequentially feeds all user turns into the graph under the same thread_id
    to simulate a real multi-turn conversation and accumulate state.
    Releases any held Redis room locks after test execution.
    """
    config = {"configurable": {"thread_id": str(uuid4())}}
    final_state = {}
    try:
        for msg in inputs.get("messages", []):
            final_state = APP.invoke(
                {"messages": [HumanMessage(content=msg)]},
                config=config
            )
    finally:
        if final_state and final_state.get("holder_id"):
            release_locks(final_state)
            
    return final_state

def single_turn_target(inputs: dict) -> dict:
    """Invokes graph for single-turn extraction tests and cleans up locks."""
    config = {"configurable": {"thread_id": str(uuid4())}}
    final_state = {}
    try:
        final_state = APP.invoke(
            {"messages": [{"role": "user", "content": inputs["messages"][0]["content"]}]},
            config=config
        )
    finally:
        if final_state and final_state.get("holder_id"):
            release_locks(final_state)
            
    return final_state


def evaluate_multi_turn_state(outputs: dict, reference_outputs: dict) -> dict:
    """
    Unified evaluator for multi-turn state, stage, and intent checks.
    Compares the graph's final accumulated state against whichever fields are present in reference_outputs.
    Normalizes dates and string casing for robust validation.
    """
    fields_to_check = [
        "intent",
        "stage",
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
    ]

    matched_fields = 0
    total_fields = 0
    comments = []

    for field in fields_to_check:
        if field not in reference_outputs:
            continue
        
        total_fields += 1
        ref = reference_outputs[field]
        pred = outputs.get(field) if isinstance(outputs, dict) else getattr(outputs, field, None)

        # Normalize date types to string format (YYYY-MM-DD)
        if isinstance(pred, date):
            pred = pred.strftime("%Y-%m-%d")

        # Case-insensitive string matching for strings/names/emails/stages/intents
        if isinstance(ref, str) and isinstance(pred, str):
            is_match = (pred.strip().lower() == ref.strip().lower())
        else:
            is_match = (pred == ref)

        if is_match:
            matched_fields += 1
            comments.append(f"✅ Matched {field} '{ref}'")
        else:
            comments.append(f"❌ {field}: expected '{ref}', got '{pred}'")

    score = (matched_fields / total_fields) if total_fields > 0 else 0.0

    return {
        "key": "state_match",
        "score": score,
        "comment": "; ".join(comments) if comments else "✅ All expected fields matched perfectly!"
    }

from agent.langsmith_tests.db_test_utils import temporary_test_database

if __name__ == "__main__":
    data = "Customer stage and intent check v1"
    evaluators = {
        "Customer multi-turn booking v1.1": evaluate_multi_turn_state,
        "Customer stage and intent check v1": evaluate_multi_turn_state,
    }
    
    evaluator_func = evaluators.get(data, evaluate_multi_turn_state)
    
    # Run against a clean, isolated, ephemeral test database with auto-cleanup
    with temporary_test_database():
        print(f"Running evaluation on '{data}'...")
        evaluate(
            multi_turn_target,
            data=data,
            evaluators=[evaluator_func],
            experiment_prefix=f"Test for {data}"
        )


