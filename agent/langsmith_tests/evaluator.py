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

# 1. Create and/or select your dataset
client = Client()
dataset_name = "Customer input and date lookup v1"

# 2. Define an evaluator
def evaluate_extraction(outputs: dict, reference_outputs: dict) -> dict:
    """
    Compares the graph's extracted fields against the reference outputs.
    Adjust the keys depending on where your graph stores the extracted data 
    (e.g., outputs["extracted_data"] or outputs["messages"][-1]).
    """
    # Assuming your graph outputs a dictionary containing the extracted fields directly:
    # e.g., {"check_in": "...", "check_out": "...", "adult_count": 2, ...}
    
    fields_to_check = ["check_in", "check_out", "adult_count", "children_count"]
    score = 1
    comments = []

    for field in fields_to_check:
        pred = outputs.get(field)
        ref = reference_outputs.get(field)
        if pred != ref:
            score = 0
            comments.append(f"Mismatch in {field}: expected {ref}, got {pred}")

    return {
        "key": "extraction_match",
        "score": score,
        "comment": "; ".join(comments) if comments else "All fields matched perfectly!"
    }

# 3. Run an evaluation
# For more info on evaluators, see: https://docs.langchain.com/langsmith/evaluation-concepts
def target_function(inputs: dict) -> dict:
    config = {"configurable": {"thread_id": str(uuid4())}}
    
    return APP.invoke(
        {"messages": [{"role": "user", "content": inputs["messages"][0]["content"]}]},
        config=config
    )
 
evaluate(
    target_function,
    data=dataset_name,
    evaluators=[evaluate_extraction],
    experiment_prefix="Customer input and date lookup experiment"
)


