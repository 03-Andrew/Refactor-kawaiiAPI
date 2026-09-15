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
            "check_in": "2026-11-10",
            "check_out": "2026-11-12",
            "adult_count": None,
            "children_count": 0,
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
            "check_in": "2026-10-11",
            "check_out": "2026-10-14",
            "adult_count": 2,
            "children_count": 0,
            "first_name": "Wilbert",
            "last_name": "Smith",
            "email": "smith@test.com",
            "phone_number": "09772394532"
        }
    },
]

multi_turn_chat = [
    {
        "inputs": {
            "messages": [
                "I'd like to book September 21 to 23 for 2 adults and 1 child",
                "I'll take a family room",
                "hold",
                "John smith, John@smith.com, 091192929292",
                "Yes, 6am"
            ]
        },
        "outputs": {
            "check_in": "2026-09-21",
            "check_out": "2026-09-23",
            "adult_count": 2,
            "children_count": 1,
            "room_type_ids": [3],
            "first_name": "John",
            "last_name": "Smith",
            "email": "John@smith.com",
            "phone_number": "091192929292",
            "avail_boat_transfer": True,
            "boat_transfer_time": "06:00",
            "stage": "confirm_booking"
        }
    },
    {
        "inputs": {
            "messages": [
                "I need a room for 2 adults from October 10 to October 12",
                "I want the Deluxe room",
                "hold",
                "Alice Brown, alice@test.com, 09171234567",
                "No"
            ]
        },
        "outputs": {
            "check_in": "2026-10-10",
            "check_out": "2026-10-12",
            "adult_count": 2,
            "children_count": 0,
            "room_type_ids": [2],
            "first_name": "Alice",
            "last_name": "Brown",
            "email": "alice@test.com",
            "phone_number": "09171234567",
            "avail_boat_transfer": False,
            "boat_transfer_time": None,
            "stage": "confirm_booking"
        }
    },
    {
        "inputs": {
            "messages": [
                "Book me a standard room for 2 adults this october 12-13",
                "hold",
                "Chris Brown",
                "chris@test.com, 09171234567",
                "No"
            ]
        },
        "outputs": {
            "check_in": "2026-10-12",
            "check_out": "2026-10-13",
            "adult_count": 2,
            "children_count": 0,
            "room_type_ids": [1],
            "first_name": "Chris",
            "last_name": "Brown",
            "email": "chris@test.com",
            "phone_number": "09171234567",
            "avail_boat_transfer": False,
            "boat_transfer_time": None,
            "stage": "confirm_booking"
        }
    },
    {
        "inputs": {
            "messages": [
                "Im Johnny Bravo, my email is johnny@email.com, my number is 0911111111. Book me a standard room for 2 adults this october 20-23",
                "hold",
                "No"
            ]
        },
        "outputs": {
            "check_in": "2026-10-20",
            "check_out": "2026-10-23",
            "adult_count": 2,
            "children_count": 0,
            "room_type_ids": [1],
            "first_name": "Johnny",
            "last_name": "Bravo",
            "email": "johnny@email.com",
            "phone_number": "0911111111",
            "avail_boat_transfer": False,
            "boat_transfer_time": None,
            "stage": "confirm_booking"
        }
    },
    {
        "inputs": {
            "messages": [
                "Book me a room for september 21 to september 19",
                "september 19 to 21",
                "4 adults"
            ]
        },
        "outputs": {
            "check_in": "2026-09-19",
            "check_out": "2026-09-21",
            "adult_count": 4,
            "children_count": 0,
            "room_type_ids": [],
            "stage": "select_and_hold_rooms",
            "first_name": None,
            "last_name": None,
            "email": None,
            "phone_number": None,
        }
    }
]

stage_and_intent_cases = [
    # 1. Pure Greetings
    {
        "inputs": {
            "messages": ["Hello! Good morning."]
        },
        "outputs": {
            "intent": "greet",
            "stage": "greet"
        }
    },
    {
        "inputs": {
            "messages": ["Hi there, I have a few questions"]
        },
        "outputs": {
            "intent": "greet",
            "stage": "greet"
        }
    },

    # 2. Pure FAQ / Policy at START
    {
        "inputs": {
            "messages": ["What is your cancellation and refund policy?"]
        },
        "outputs": {
            "intent": "rag_node",
            "stage": "greet"
        }
    },
    {
        "inputs": {
            "messages": ["Are pets allowed in the resort?"]
        },
        "outputs": {
            "intent": "rag_node",
            "stage": "greet"
        }
    },
    {
        "inputs": {
            "messages": ["How much is the cheapest room per night?"]
        },
        "outputs": {
            "intent": "rag_node",
            "stage": "greet"
        }
    },
    {
        "inputs": {
            "messages": ["Can we bring our own alcoholic drinks? How much is corkage?"]
        },
        "outputs": {
            "intent": "rag_node",
            "stage": "greet"
        }
    },
    {
        "inputs": {
            "messages": ["What time is standard check in and check out?"]
        },
        "outputs": {
            "intent": "rag_node",
            "stage": "greet"
        }
    },

    # 3. Direct Booking Intent at START
    {
        "inputs": {
            "messages": ["I'd like to book a room for 2 adults from October 10 to 12"]
        },
        "outputs": {
            "intent": "book",
            "stage": "select_and_hold_rooms"
        }
    },

    # 4. Mid-Flow FAQ Interruption during Boat Transfer Stage
    {
        "inputs": {
            "messages": [
                "I want to book for 2 adults this October 20 to 22",
                "I'll take the Deluxe room",
                "hold",
                "Wilbert Smith, wilbert@gmail.com, 09171234567",
                "Wait, can I bring my dog to the resort?"
            ]
        },
        "outputs": {
            "intent": "rag_node",
            "stage": "collect_boat_transfer"
        }
    },
    {
        "inputs": {
            "messages": [
                "Book 2 adults from October 20 to 22",
                "Deluxe room",
                "hold",
                "Wilbert Smith, wilbert@gmail.com, 09171234567",
                "Is boat transfer free for Deluxe rooms?"
            ]
        },
        "outputs": {
            "intent": "rag_node",
            "stage": "collect_boat_transfer"
        }
    },

    # 5. Normal Stage Answer during Boat Transfer (Must NOT be flagged as FAQ)
    {
        "inputs": {
            "messages": [
                "Book 2 adults from October 20 to 22",
                "Deluxe room",
                "hold",
                "Wilbert Smith, wilbert@gmail.com, 09171234567",
                "Yes, please schedule it for 8 AM"
            ]
        },
        "outputs": {
            "intent": "book",
            "stage": "confirm_booking"
        }
    },
    {
        "inputs": {
            "messages": [
                "Book 2 adults from October 20 to 22",
                "Deluxe room",
                "hold",
                "Wilbert Smith, wilbert@gmail.com, 09171234567",
                "No"
            ]
        },
        "outputs": {
            "intent": "book",
            "stage": "confirm_booking"
        }
    },

    # 6. Mid-Flow FAQ Interruption during Room Selection Stage
    {
        "inputs": {
            "messages": [
                "I need a room for 4 adults from November 1 to November 3",
                "What amenities are included in the Family Room?"
            ]
        },
        "outputs": {
            "intent": "rag_node",
            "stage": "select_and_hold_rooms"
        }
    },

    # 7. Mid-Flow FAQ Interruption during Customer Info Stage
    {
        "inputs": {
            "messages": [
                "I need a room for 2 adults from October 15 to 17",
                "Deluxe Room",
                "hold",
                "Do you have high speed WiFi in the rooms?"
            ]
        },
        "outputs": {
            "intent": "rag_node",
            "stage": "collect_customer_info"
        }
    },

]

client = Client()

def upload_datasets():
    # 1. Single-turn extraction dataset
    single_turn_name = "Customer input and date lookup v1"
    if not client.has_dataset(dataset_name=single_turn_name):
        ds1 = client.create_dataset(
            dataset_name=single_turn_name,
            description="Parse user dates and guest count inputs"
        )
        client.create_examples(
            dataset_id=ds1.id,
            examples=extract_and_search_rooms
        )
        print(f"Created single-turn dataset: {single_turn_name}")
    else:
        print(f"Dataset '{single_turn_name}' already exists.")

    # 2. Multi-turn conversation dataset
    multi_turn_name = "Customer multi-turn booking v1.1"
    if not client.has_dataset(dataset_name=multi_turn_name):
        ds2 = client.create_dataset(
            dataset_name=multi_turn_name,
            description="Evaluate multi-turn booking agent state progression"
        )
        client.create_examples(
            dataset_id=ds2.id,
            examples=multi_turn_chat
        )
        print(f"Created multi-turn dataset: {multi_turn_name}")
    else:
        print(f"Dataset '{multi_turn_name}' already exists.")

    # 3. Stage and Intent check dataset
    stage_intent_name = "Customer stage and intent check v1"
    if not client.has_dataset(dataset_name=stage_intent_name):
        ds3 = client.create_dataset(
            dataset_name=stage_intent_name,
            description="Evaluate intent classification and stage persistence across greetings, FAQs, and booking stages"
        )
        client.create_examples(
            dataset_id=ds3.id,
            examples=stage_and_intent_cases
        )
        print(f"Created stage and intent dataset: {stage_intent_name}")
    else:
        print(f"Dataset '{stage_intent_name}' already exists.")

if __name__ == "__main__":
    upload_datasets()