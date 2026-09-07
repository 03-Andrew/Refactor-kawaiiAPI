from langsmith import Client
from dotenv import load_dotenv

load_dotenv()

extract_and_search_rooms = [
    {
        "inputs":{
            "messages": [
                {
                    "role": "user",
                    "content": "I'd like to book September 21 to 23 for 2 adults and 1 child"
                }
            ]
        },
        "outputs": {
            "check_in": "2026-09-21",
            "check_out": "2026-09-23",
            "adult_count": 2,
            "children_count": 1
        }
    },
    {
        "inputs":{
            "messages": [
                {
                    "role": "user",
                    "content": "September 25 to September 27, 2 adults."
                }
            ]
        },
        "outputs": {
            "check_in": "2026-09-25",
            "check_out": "2026-09-27",
            "adult_count": 2,
            "children_count": 0
        }
    },
     {
        "inputs": {
            "messages": [
                {
                    "role": "user",
                    "content": "I need a room for 4 adults and 2 children from October 3 to October 5."
                }
            ]
        },
        "outputs": {
            "check_in": "2026-10-03",
            "check_out": "2026-10-05",
            "adult_count": 4,
            "children_count": 2
        }
    },
    {
        "inputs": {
            "messages": [
                {
                    "role": "user",
                    "content": "Can I book from November 10 until November 12?"
                }
            ]
        },
        "outputs": {
            "stage": "search_available_rooms",
            "missing_information": [
                "adult_count"
            ]
        }
    },
    {
        "inputs": {
            "messages": [
                {
                    "role": "user",
                    "content": "My name is Wilbert Smith, my email is smith@test.com, my phone number is 09772394532. I'd like to book a room for 2 adults this October 11-14"
                }
            ]
        }, 
        "outputs": {
            "check_in": "2026-10-03",
            "check_out": "2026-10-05",
            "adult_count": 4,
            "children_count": 2,
            "first_name": "Wilbert",
            "last_name": "Smith",
            "email": "smith@test.com",
            "phone_number": "09772394532"
        }
    },
]

client = Client()

dataset_name = "Customer input and date lookup 2"

dataset = client.create_dataset(
    dataset_name=dataset_name, description="Parse user inputs"
)

client.create_examples(
    dataset_id=dataset.id,
    examples=extract_and_search_rooms
)