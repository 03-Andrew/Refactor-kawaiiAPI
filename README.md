# Kawaii API

Hotel booking and management API built with Django REST Framework.

## Stack

- **Python** 3.9+
- **Django** 6.0
- **Django REST Framework** 3.17
- **Channels** + **Daphne** (WebSockets)
- **SQLite** (dev) / PostgreSQL (prod via `dj-database-url`)
- **django-cors-headers** (CORS)
- **SimpleJWT** (auth)
- **PayMongo** (payments)
- **SSE** via `django-eventstream`

## Apps

| App | Purpose |
|---|---|
| `bookings` | Rooms, room types, availability, online/stay-in/day-tour bookings |
| `transactions` | Billing, payments, guests, food bills, additional payments |
| `receptionist` | Room status, approve/pending bookings, amenities, activities |
| `user` | Login, signup, JWT tokens |
| `paymongo` | Payment links, webhooks |
| `reports` | Daily, weekly, monthly, yearly revenue reports |

## Setup

```bash
# Clone and cd
git clone <repo-url> && cd Refactor-kawaiiAPI

# Create virtualenv
python -m venv venv && source venv/bin/activate

# Install deps
pip install -r requirements.txt

# Migrate
python manage.py migrate

# Run
python manage.py runserver
```

## API Docs

- Swagger UI: `/api/docs/`
- ReDoc: `/api/redoc/`
- OpenAPI schema: `/api/schema/`

## Health Check

`GET /api/health/` — no auth required.

## Environment Variables

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Django secret key |
| `PAYMONGO_SECRET_KEY` | PayMongo API key |
| `PAYMONGO_WEBHOOK_SECRET` | PayMongo webhook secret |
| `EMAIL_HOST` | SMTP host |
| `EMAIL_HOST_USER` | SMTP user |
| `EMAIL_HOST_PASSWORD` | SMTP password |
| `EMAIL_PORT` | SMTP port |
| `EMAIL_USE_TLS` | SMTP TLS (`True`/`False`) |
| `EMAIL_BACKEND` | Django email backend |

## WebSocket

`ws://<host>/ws/receptionist/` — receptionist dashboard real-time updates.
