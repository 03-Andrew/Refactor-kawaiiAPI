# Resort Booking Platform: Backend Overhaul & AI Reservation System

> Comprehensive backend refactoring, query optimization, and conversational AI booking layer

---

## Project Overview
This project represents the **evolution of an end-to-end resort reservation and guest management system** originally developed by a collaborative team (team of 5).

A comprehensive **backend refactor and architectural overhaul** of a resort booking and reservation platform built with **Django REST Framework**, **LangGraph**, **Celery**, and **Redis**, backed by **PostgreSQL** on **AWS**.

Originally developed with monolithic fat views, N+1 query bottlenecks, and double-booking race conditions during high-concurrency booking windows, the reservation engine was overhauled:
- **Query Optimization & Database Overhaul**: Replaced legacy N+1 query patterns with batch prefetching and query optimization across 10 core booking and availability endpoints, cutting worst-case query counts from 2,103 down to 12 (a 78% to 99.5% reduction on benchmark tests).
- **Concurrency & Double-Booking Protection**: Implemented a distributed locking mechanism using **Redis** with automated TTL expiry to hold room inventory and eliminate race conditions during checkout.
- **Asynchronous Task Queuing**: Offloaded PayMongo payment webhook processing, payment verification, and automated booking confirmation emails to **Celery** workers backed by Redis.
- **Conversational AI Booking Pipeline & RAG Policy Assistant**: Built a multi-turn conversational reservation agent on top of the booking backend using **LangGraph** and **Google Gemini** / **OpenAI**, featuring structured Pydantic extraction, conversational backtracking, and a RAG FAQ & policy retrieval system utilizing **structure-aware Markdown header chunking**.
- **Observability & Multi-Turn State Testing**: Integrated **LangSmith** for real-time agent trace visualization, latency monitoring, token accounting, and multi-turn state regression testing across reservation flows.
- **Production-Ready AWS Architecture**: Containerized services with **Docker Compose**, designed a dedicated **AWS VPC** architecture with separated public/private subnets, EC2 application hosting, AWS RDS PostgreSQL, and Nginx reverse proxy configuration.

---

## System Architecture

```
                                      [ Clients / Web / Chat UI ]
                                                   │
                                                   ▼
                                         [ Nginx Reverse Proxy ]
                                                   │
                                                   ▼
                                       HTTP / REST API Requests
                                                   │
                                                   ▼
                                 ┌───────────────────────────────────┐
                                 │    Django REST Framework API      │
                                 │   (Service Layer & API Views)     │
                                 └───────────────┬───────────────────┘
                                                 │
                  ┌──────────────────────────────┼──────────────────────────────┐
                  │                              │                              │
                  ▼                              ▼                              ▼
          ┌───────────────┐              ┌───────────────┐             ┌──────────────────┐
          │  PostgreSQL   │              │  Redis Locks  │             │ LangGraph Agent  │
          │   (AWS RDS)   │              │   & Caching   │             │ (Gemini / RAG)   │
          └───────▲───────┘              └───────┬───────┘             └────────┬─────────┘
                  │                              │                              │
                  │                       ┌──────▼────────┐                     ▼
                  └───────────────────────┤ Celery Worker ├─────────────► [ LangSmith Tracing ]
                                          │  (PayMongo)   │
                                          └───────────────┘
```

---

## Conversational AI Booking Pipeline (LangGraph)

The AI booking agent (`agent/agent2.py`) coordinates multi-stage guest reservation flows using a deterministic finite-state graph with Pydantic extraction schemas:

```
START
  └─► route_stage()
        ├─► greet_user
        ├─► search_available_rooms
        ├─► select_and_hold_rooms    ──► [ Redis Distributed Room Lock ]
        ├─► collect_customer_info
        ├─► collect_boat_transfer
        ├─► rag_node (FAQ / Policies)──► [ Structure-Aware Markdown Chunking ]
        └─► confirm_booking
                └─► route_booking_confirmation()
                        ├─► create_online_booking ──► END
                        └─► release_locks ──► END (Cancelled)
```

### Key Agent Capabilities:
- **Pydantic Structured Output**: Guarantees deterministic state schema transformations across multi-turn chats.
- **Conversational Backtracking**: Guests can backtrack, switch dates, modify guest counts, or release held rooms at any stage via `handle_common_back_action()`.
- **RAG Policy & FAQ QA**: Structure-aware chunking parses markdown headers (`#`, `##`, tables) to preserve semantic policy boundaries for resort rules, amenities, and boat transfers.
- **LangSmith Tracing**: Full multi-turn evaluation, latency monitoring, and state inspection.

---

## Tech Stack

| Domain | Technologies |
|---|---|
| **Core Backend** | Python 3.11+, Django 6.0, Django REST Framework 3.17 |
| **AI & LLMs** | LangGraph, LangSmith, Google Gemini / OpenAI API, Pydantic |
| **Concurrency & Async** | Redis, Celery (PayMongo webhooks, email dispatch) |
| **Database & Cache** | PostgreSQL (AWS RDS), SQLite (dev), Redis Key-Value TTL Cache |
| **Payments** | PayMongo API (Payment Intents, Webhooks, HMAC verification) |
| **Infrastructure & DevOps** | Terraform (IaC), Docker, Docker Compose, AWS EC2, AWS VPC, AWS RDS, Nginx |
| **Authentication & Docs** | SimpleJWT, drf-spectacular (OpenAPI 3.0 / Swagger / ReDoc) |

---

## Project Structure

```
├── agent/                  # LangGraph AI Booking Agent & RAG Policy System
│   ├── agent2.py           # Active LangGraph state graph definition
│   ├── nodes.py            # Graph node implementations & routing logic
│   ├── states.py           # Pydantic schemas & TypedDict BookingState
│   ├── views.py            # Chat API endpoint invoking the compiled graph
│   └── rag/                # RAG knowledge base & policy retrieval system
│       ├── agent.py        # RAG query execution & vector search pipeline
│       ├── md_loader.py    # Markdown header chunking & ChromaDB vector ingestion
│       └── resort_policies.md # Mock policy & FAQ knowledge base (used for testing only)
├── bookings/               # Room inventory, availability services & reservations
│   ├── services/           # Decoupled business logic (locking, search, checkout)
│   └── models.py           # Room, RoomType, Booking models
├── infra/                  # Terraform Infrastructure as Code (AWS VPC, EC2, RDS PostgreSQL, SGs)
│   ├── vpc.tf              # AWS VPC, public/private subnets, internet gateway
│   ├── ec2.tf              # EC2 application instance provisioning
│   ├── rds.tf              # AWS RDS PostgreSQL instance & subnet group
│   └── sg.tf               # Security groups & ingress/egress rules
├── transactions/           # Billing, guest records, food orders, additional charges
├── receptionist/           # Front-desk reservation endpoints, check-in flows
├── paymongo/               # PayMongo integration, payment links, Celery webhooks
├── reports/                # Revenue reporting (daily, weekly, monthly, annual)
├── user/                   # Authentication & user profile management
├── docker-compose.yml      # Container orchestration for App, Redis, and Celery worker
└── DockerFile              # Base container configuration
```

---

## Quick Start

### 1. Prerequisites
- Docker & Docker Compose **or** Python 3.11+ with Redis server installed locally.

### 2. Environment Configuration
Create a `.env` file in the root directory:

```env
# --- Django Core Configuration ---
SECRET_KEY=''                       # Django secret key (e.g. run: python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')
DEBUG='True'                        # Set to 'True' for local development, 'False' for production
DATABASE_URL=''                     # PostgreSQL connection URL (e.g. postgres://user:password@localhost:5432/kawaii_db)

# --- Cloudflare Turnstile Bot Protection ---
TURNSTILE_SECRET_KEY=''             # Cloudflare Turnstile secret key for captcha verification

# --- PayMongo Payment Gateway ---
PAYMONGO_SECRET_KEY=''              # PayMongo secret API key (starts with sk_test_... or sk_live_...)
PAYMONGO_WEBHOOK_SECRET=''          # PayMongo webhook secret key for HMAC signature verification (whsk_...)
PAYMONGO_PUBLIC_KEY=''              # PayMongo public API key (starts with pk_test_... or pk_live_...)

# --- Email / SMTP Configuration ---
EMAIL_HOST='smtp.gmail.com'         # SMTP host (default: smtp.gmail.com)
EMAIL_HOST_USER=''                  # Gmail / SMTP username (e.g. your-email@gmail.com)
EMAIL_HOST_PASSWORD=''              # Gmail App Password (16 characters, 2FA enabled)
EMAIL_PORT=587                      # SMTP port (587 for TLS, 465 for SSL)
EMAIL_USE_TLS='True'                # Enable TLS encryption ('True' or 'False')
EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend' # Django email backend path

# --- LLM & AI Agent Provider Keys ---
GOOGLE_API_KEY=''                   # Google Gemini API key (from Google AI Studio)
OPENAI_API_KEY=''                   # OpenAI API key (sk-..., used for RAG embeddings / LLM)

# --- LangSmith Observability & Tracing ---
LANGSMITH_TRACING=true              # Enable LangSmith tracing (true / false)
LANGSMITH_ENDPOINT='https://apac.api.smith.langchain.com' # LangSmith API endpoint (APAC or default US: https://api.smith.langchain.com)
LANGSMITH_API_KEY=''                # LangSmith personal API key (lsv2_pt_...)
LANGSMITH_PROJECT=''                # LangSmith project name for grouping traces
LANGSMITH_TRACING_V2=true           # Enable LangSmith V2 tracing pipeline
```

### 3. Run with Docker Compose (Recommended)

```bash
# Build and start App, Celery worker, and Redis
docker-compose up --build
```

### 4. Manual Local Setup

```bash
# Setup virtual environment
python -m venv .venv && source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Start Redis & Celery worker (in separate terminal)
celery -A kawaiiAPI worker -l info

# Start Django development server
python manage.py runserver
```

---

## API & Documentation

Once the server is running:
- **Swagger UI**: `http://localhost:8000/api/docs/`
- **ReDoc**: `http://localhost:8000/api/redoc/`
- **OpenAPI Schema**: `http://localhost:8000/api/schema/`
- **Health Check**: `GET /api/health/`
