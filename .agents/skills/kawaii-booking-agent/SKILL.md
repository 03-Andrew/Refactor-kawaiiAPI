---
name: kawaii-booking-agent
description: >-
  Use this skill when working on the LangGraph AI booking agent in this project.
  Covers architecture, node conventions, state management, graph flow, adding new nodes,
  debugging agent behavior, and understanding the booking pipeline.
---

# Kawaii Resort Booking Agent

A **LangGraph + Google Gemini** powered conversational booking agent embedded in a Django REST backend.
The agent guides guests through a fixed multi-stage booking pipeline using structured LLM output extraction.

---

## File Map

| File | Purpose |
|---|---|
| `agent/agent2.py` | **Active** graph definition — nodes, edges, compilation |
| `agent/nodes.py` | All node functions + routing logic |
| `agent/states.py` | `BookingState` TypedDict + all Pydantic input schemas |
| `agent/agent.py` | Old/prototype agent — not in use |
| `agent/views.py` | Django view that invokes the compiled `APP` graph |

---

## Graph Flow

```
START
  └─► route_stage()  ← decides which node to run based on state["stage"]
        ├─► greet
        ├─► search_available_rooms
        ├─► select_and_hold_rooms
        ├─► collect_customer_info
        ├─► collect_boat_transfer
        └─► confirm_booking
                └─► route_booking_confirmation()
                        ├─► book ──► END
                        └─► END (cancelled)
```

Each node sets `stage` in its return dict to drive the **next** invocation routing.

---

## LLM Setup

```python
# nodes.py:87
llm = ChatGoogleGenerativeAI(
    model="gemini-3.1-flash-lite",
    temperature=0,  # probabilistic — consider 0 for extraction nodes
    max_retries=2,
)
```

- All extraction uses `llm.with_structured_output(SomePydanticSchema)`
- Free-form replies use `llm.invoke(prompt)`
- Token usage is capped via `get_recent_messages(state, window_size=6)`

---

## State: `BookingState`

Defined in `states.py`. Key fields:

| Field | Type | Purpose |
|---|---|---|
| `messages` | `list[AnyMessage]` | Full conversation history (append-only via `add_messages`) |
| `stage` | `Literal[...]` | Drives `route_stage()` routing |
| `check_in` / `check_out` | `date or None` | Booking dates |
| `adult_count` / `children_count` | `int or None` | Guest counts |
| `room_type_ids` | `list[int]` | Selected room type IDs (may repeat for multiple rooms) |
| `holder_id` | `str or None` | Redis lock holder ID |
| `confirmed` | `bool or None` | User final booking confirmation |
| `first_name`, `last_name`, `email`, `phone_number` | `str or None` | Guest contact info |
| `avail_boat_transfer` | `bool or None` | Whether boat transfer was requested |
| `boat_transfer_time` | `str or None` | 24h format time string e.g. "08:00" |

---

## Pydantic Schemas (in `states.py`)

All inherit from `BaseStageInput` which includes a common `action` field:

```python
action: Literal["continue", "change_room", "modify_dates_or_guests", "cancel"]
```

Used in every node to detect if the user wants to go back/cancel mid-flow via `handle_common_back_action()`.

| Schema | Used In |
|---|---|
| `InitalGreetingState` | `greet_user` |
| `DateAndGuestCountInput` | `search_available_rooms` |
| `SelectedRoomsInput` | `select_and_hold_rooms` |
| `GuestInfo` | `collect_customer_info` |
| `AvailBoat` | `collect_boat_transfer` |
| `ConfirmBooking` | `confirm_booking` |

---

## Node Conventions

Every node must:
1. Return a **partial `BookingState` dict** — only include keys being updated
2. Set `"stage"` to drive the next routing decision
3. Append to `"messages"` with `AIMessage(content=...)`
4. Call `handle_common_back_action(state, result)` if `result.action != "continue"`

### Pattern for an extraction node:
```python
def my_node(state: BookingState):
    result = llm.with_structured_output(MySchema).invoke([
        {"role": "system", "content": "..."},
        *get_recent_messages(state, window_size=6)
    ])

    if result.action != "continue":
        return handle_common_back_action(state, result)

    # ... validation logic ...

    return {
        "some_field": result.some_field,
        "stage": "next_stage_name",
        "messages": [AIMessage(content="...")]
    }
```

---

## Adding a New Node

1. **Define the Pydantic schema** in `states.py` (extend `BaseStageInput`)
2. **Add the field(s)** to `BookingState` if new state is needed
3. **Write the node function** in `nodes.py` following the pattern above
4. **Register in `agent2.py`**:
   ```python
   graph.add_node('my_node', my_node)
   graph.add_edge('previous_node', 'my_node')
   ```
5. **Add the stage name** to `route_stage()` in `nodes.py`
6. **Import** the node in `agent2.py`

---

## Key Service Functions

All imported from `bookings/services/`:

| Function | Purpose |
|---|---|
| `get_room_types_availability(check_in, check_out, guest_count)` | Live DB availability query |
| `get_room_type_basic_info()` | All room types (cached via `ROOM_CACHE`) |
| `bulk_lock_room_type(rooms_to_lock)` | Redis lock — returns `{all_held, holder_id, failures}` |
| `release_holder_locks(rooms, holder_id)` | Release Redis lock on back/cancel |
| `create_online_booking(customer, rooms, boat_details, holder_id)` | Final DB booking creation |

---

## Room Cache

`ROOM_CACHE` is a module-level `RoomCacheSchema` in `nodes.py`. It caches room type data for **1 hour** to avoid repeated DB hits. Invalidates automatically on TTL expiry.

---

## Boat Transfer

- Times must be converted to 24h format via `convert_to_24h()` before storing
- Valid slots: `06:00`, `08:00`, `10:00`, `12:00`, `15:00`, `17:00`
- `head_count` = `adult_count + children_count`

---

## Checkpointer

`MemorySaver` is used — state persists per `thread_id` within a process lifetime only (in-memory).
For production persistence, replace with `PostgresSaver` or `RedisSaver`.

---

## Common Debugging Tips

- **Agent goes to wrong stage**: Check `route_stage()` — the `stage` field in the returned state dict is the source of truth
- **LLM not extracting correctly**: Lower `temperature` to `0` for that specific node
- **Redis lock failing**: Check `RedisUnavailable` exception handling in `select_and_hold_rooms`
- **Back-action not triggering**: Ensure the system prompt instructs the LLM to set the `action` field
