# KawaiiAPI — Current State Assessment

> Generated 2026-07-21. Pre-refactor baseline of issues, risks, and anti-patterns.

---

## 1. Security (CRITICAL — fix before anything else)

### 1.1 Hardcoded Secrets in `kawaiiAPI/settings.py`

| Secret | Line | Risk |
|--------|------|------|
| `SECRET_KEY` | Plaintext in repo | Session hijacking, signed data forgery |
| `PAYMONGO_SECRET_KEY` | `sk_test_Y4Sv1NEcDmqXYmkzfVa9L5uF` | Full PayMongo API access |
| `PAYMONGO_WEBHOOK_SECRET` | `whsk_cun6XeqBp5gf23bAXttwiXGA` | Webhook spoofing |
| `EMAIL_HOST_PASSWORD` | `jcjm lhxg ljsg lthk` | Gmail account compromise |

Database credentials in **commented-out code** (lines ~85–130): DigitalOcean PostgreSQL user/password, Supabase user/password, Railway password. Still visible in git history even if commented.

### 1.2 `.env` File Committed

`.env` at repo root contains a live DigitalOcean PostgreSQL connection string with credentials. This file is **not** in `.gitignore` or is already tracked.

### 1.3 `DEBUG = True` (line 26)

Running in production with DEBUG on exposes stack traces, settings, and environment variables to end users.

### 1.4 CORS Middleware Ordering

`CorsMiddleware` is placed **after** `CommonMiddleware` (line 47). Per django-cors-headers docs, it must be **before** `CommonMiddleware` and as high as possible.

### 1.5 CSRF Configuration

`CSRF_TRUSTED_ORIGINS` includes 5 origins but `CSRF_COOKIE_SECURE`, `CSRF_COOKIE_HTTPONLY`, `CSRF_USE_SESSIONS`, and `SECURE_SSL_REDIRECT` are all **commented out**. No HTTPS enforcement.

---

## 2. Architecture

### 2.1 No Settings Split

Single `settings.py` with hardcoded values, commented-out configs, and no `dev`/`staging`/`prod` split. Every environment change requires editing code.

### 2.2 Business Logic in Views (Fat Views)

`bookings/views.py` — 4 helper functions + 10 class-based views in one file.
`receptionist/views.py` — 16 class-based views + helper functions.
`transactions/views.py` — 18 class-based views.
`paymongo/views.py` — HMAC validation, webhook processing, payment creation, email sending all inline.

No service layer, no repository pattern, no separation of concerns. Views handle validation, business rules, external API calls, and DB operations directly.

### 2.3 Empty Models Where Logic Should Live

- `receptionist/models.py` — empty (`# Create your models here.`)
- `reports/models.py` — empty (`# Create your models here.`)

Receptionist serializers import from `bookings` and `transactions` models — cross-app coupling without clear ownership.

### 2.4 Model Typo: `AdditonalPayment`

`transactions/models.py` — model name is `AdditonalPayment` (missing "i" in "Additional"). This typo propagates to:
- Serializer: `AdditionalPaymentSerializer` (inconsistent — serializer uses correct spelling)
- Related name: `additional_payment` (on Billing FK)
- Database table: whatever Django auto-generates

### 2.5 No API Versioning

All 6 apps mount at root (`path('', include('...urls'))`). No `/api/v1/` prefix. Any breaking change breaks all consumers.

### 2.6 Inconsistent URL Patterns

All apps use `path('', ...)` — flat namespace, no prefix per app. URL conflicts possible between apps.

---

## 3. Booking System — Double-Booking Risk

### 3.1 No Distributed Lock

`CreateStayInBooking` and `CreateOnlineBooking` check room availability and create bookings, but there is no Redis lock or database-level lock preventing two concurrent requests from booking the same room for overlapping dates.

### 3.2 `unique_together` Constraint

Booking model has `unique_together = ('room', 'check_in', 'check_out')` — this prevents exact duplicate rows but does **not** prevent overlapping date ranges (e.g., Room 1 booked Jan 1–5 and Jan 3–7).

### 3.3 Availability Check Logic

`AvailableRoomTypes` view computes availability by counting total rooms minus overlapping bookings. This is a read-then-write race condition at the application level. Two concurrent POSTs can both pass the availability check before either writes.

### 3.4 What's Needed

- Redis-based distributed lock per room + date range during booking creation
- Database-level constraint or `select_for_update` on room rows
- Atomic transaction wrapping availability check + booking creation

---

## 4. Background Processing

### 4.1 Celery Listed but Unused

`requirements.txt` includes `celery==5.4.0`, `kombu==5.4.2`, `redis==5.1.1`, `billiard==4.2.1`, `vine==5.1.0`. But:
- No `tasks.py` in any app
- No `celery.py` config in project root
- No Celery worker in `docker-compose.yml`
- No `Procfile` entry for Celery worker

### 4.2 Unsafe Threading in Webhook

`paymongo/views.py` `WebhookNotif.post()` spawns a **raw Python thread** to call `process_event()`. Django's ORM is not thread-safe by default. Database connections are not managed across threads. If the main request completes before the thread, the connection may be closed.

### 4.3 What's Needed

- Proper Celery configuration (`celery.py`, task discovery)
- Move `process_event()`, `create_payment()`, `send_email()` to Celery tasks
- Add Celery worker + beat to `docker-compose.yml`
- Replace threading in `WebhookNotif` with `.delay()` calls

---

## 5. Database

### 5.1 SQLite for Production

`settings.py` defaults to SQLite (`db2.sqlite3`). SQLite does not handle concurrent writes well. Not suitable for a multi-user booking system.

### 5.2 Multiple Database Files

- `db.sqlite3` — 0 bytes (empty)
- `db2.sqlite3` — active database
- `..testDb/cleadb.sqlite3`, `clean_db.sqlite3`, `clean_db2.sqlite3`, `clean.sqlite3` — test remnants

Active DB and test DBs are not clearly separated.

### 5.3 Commented-Out Database Configs

Settings file contains **5 different database configurations** commented out: DigitalOcean (2), Supabase, Railway, and local Docker PostgreSQL. This is confusing and indicates no single source of truth.

### 5.4 Hardcoded PostgreSQL Credentials

All commented-out configs include real credentials in plaintext. These need scrubbing from git history.

---

## 6. Code Quality

### 6.1 Commented-Out Code

Heavy presence of dead code:
- `bookings/views.py` — entire "Trash code" block at bottom
- `paymongo/views.py` — `CardPayment` and `GCashSource` classes commented out
- `paymongo/serializers.py` — `CardPaymentSerializer` and `GCashSourceSerializer` commented out
- `reports/views.py` — `GetMonthlyReports` and `GetWeeklyReports` commented out
- `kawaiiAPI/settings.py` — 50+ lines of commented database/email/CSRF config

### 6.2 Magic Numbers Everywhere

Booking/billing statuses referenced as integers throughout codebase:
- `status=1` (pending), `status=2` (approved/confirmed), `status=3`, `status=4`, `status=5` (cancelled)
- `status_id=3` in `ListBillingBooking` queryset
- `status='a'` → maps to `status_id=2`, `status='p'` → maps to `status_id=1`
- `room_status=1` (available)
- `is_booked` boolean derived from status checks

No constants, no enum, no `choices` on model fields. Changing a status value requires finding every magic number across 6 apps.

### 6.3 Serializer Explosion

48+ serializer classes with numbered variants:
- `BookingSerializer`, `BookingSerializer2`, `BookingSerializer3`
- `RoomTypeSerializer`, `RoomTypeSerializer2`, `RoomTypeSerializer3`
- `RoomSerializer`, `RoomSerializer2`
- `RoomAllSerializer`, `RoomStatusAllSerializer`
- `AvailableRoomSerializer`, `AvailableRoomSerializer2`
- `AmenitiesAvailedSerializer`, `AmenitiesAvailedSerializer2`, `AmenitiesAvailedSerializer3`
- `FoodBillSerializer`, `FoodBillSerializer2`
- `CustomerSerializer`, `CustomerSerializer2`
- `PaymentSerializer`, `PaymentSerializer2`
- `GuestListSerializer`, `GuestListSerializerAll`

No clear reason for N+1 variants. Naming conveys zero semantic meaning.

### 6.4 Inconsistent View Patterns

Mix of:
- `generics.ListAPIView` / `generics.ListCreateAPIView` / `generics.RetrieveUpdateDestroyAPIView`
- `APIView` with manual `get()` / `post()` / `patch()`
- Function-based `@api_view` views (user app)
- Plain Django `View` (`WebSocketTestView`)

No consistent pattern for filtering, pagination, or error responses.

### 6.5 No Type Hints

Zero type annotations across the entire codebase. Unclear what any function accepts or returns.

### 6.6 No Docstrings

No function, class, or module docstrings anywhere. The only docstring is Django's auto-generated project header in `settings.py`.

### 6.7 Inconsistent Naming

- `BookingsAllSerializer` vs `RoomAllSerializer` (plural vs singular)
- `BillingSerializerBase` (only one with "Base" suffix)
- `RoomTypeSerializer3` serializes `BookingStatus`, not `RoomType`
- `RoomStatusAllSerializer` serializes `Room`, not `RoomStatus`
- `BillingDetailSerializer` vs `BillingSerializer` vs `BillingAllSerializer` vs `BillingSerializerBase` vs `BillingGuestList`

### 6.8 Hardcoded External URLs

- `https://seal-app-nvafi.ondigitalocean.app/api/payment-link/` (bookings/views.py)
- `https://kawaii-app-nb6lb.ondigitalocean.app/api/billing-details/{id}/` (paymongo/views.py)
- `https://api.paymongo.com/v1/links` (paymongo/views.py)

No configuration, no environment variable fallback, no service discovery.

---

## 7. Testing

### 7.1 Placeholder Test Files

Every app has `tests.py` but from the project structure and code patterns, these likely contain minimal or no real tests. No `pytest` or `coverage` in requirements.

### 7.2 No Test Database Configuration

`..testDb/` directory exists outside project root with multiple SQLite files. No test settings, no CI pipeline, no test runner configuration.

---

## 8. Infrastructure & DevOps

### 8.1 docker-compose.yml Gaps

- No database service (relies on SQLite file on host)
- No Celery worker service
- No Celery beat service
- No health checks on any service
- `DEBUG: "False"` but `SECRET_KEY` hardcoded (contradicts production readiness)
- No volume for SQLite data persistence
- No `.env` file mounting or env_file declaration

### 8.2 Multiple Deployment Targets

- `vercel.json` — Vercel deployment
- `Procfile` — Heroku (runs `daphne`)
- `DockerFile` + `docker-compose.yml` — Docker
- Commented database configs for: DigitalOcean (×2), Supabase, Railway

No single deployment strategy. Configuration for each target is incomplete.

### 8.3 No Logging Configuration

`settings.py` has no `LOGGING` dict. No structured logging, no log levels, no log aggregation.

### 8.4 `requirements2.txt`

Second requirements file with duplicates + additional packages (supabase, aiohttp, httpx, pydantic). Unclear which is authoritative. Supabase packages suggest abandoned migration attempt.

---

## 9. Authentication & Authorization

### 9.1 Mixed Auth Patterns

- `user/views.py` — JWT (simplejwt) + DRF Token authentication
- `reports/views.py` — JWT protected (`permission_classes = [IsAuthenticated]`)
- Other views — no authentication at all (open API)

No consistent auth strategy. Some endpoints public, some JWT, same codebase no middleware enforcement.

### 9.2 Custom User Model Not Used

`AUTH_USER_MODEL = "user.CustomUser"` is **commented out** (settings.py line ~175). Django's default `User` model is used with a `UserProfile` OneToOne extension. Changing this later requires migration reset.

### 9.3 Signup View Creates DRF Token

`user/views.py` `signup()` creates a DRF `Token` instead of JWT. Login returns JWT. Inconsistent.

---

## 10. Documentation

### 10.1 README.md

Current README is minimal — no setup instructions, no API documentation, no architecture overview, no environment variable reference.

### 10.2 No API Documentation

Despite using DRF, there is no Swagger/OpenAPI schema generation (though `rest_framework_swagger` is in INSTALLED_APPS). No `get_schema_view()` configured.

---

## 11. Priority Action Items

### Immediate (security — day 0)
1. Rotate all exposed secrets (SECRET_KEY, PayMongo, Gmail, DB passwords)
2. Move all secrets to environment variables
3. Add `.env` to `.gitignore`
4. Set `DEBUG = False` for production
5. Fix CORS middleware ordering
6. Scrub git history of hardcoded credentials

### High (correctness — week 1)
7. Implement Redis-based double-booking lock
8. Add `select_for_update` or DB constraint for overlapping bookings
9. Set up Celery for background tasks (webhook processing, emails)
10. Replace thread-based webhook processing with Celery tasks
11. Add proper settings split (base/dev/prod)

### Medium (quality — week 2–3)
12. Extract service layer from views
13. Replace magic numbers with constants/enums
14. Consolidate serializers — remove numbered variants, use context/serializer fields
15. Add API versioning (`/api/v1/`)
16. Fix model typo (`AdditonalPayment` → `AdditionalPayment`)
17. Add proper logging configuration

### Lower (polish — week 3+)
18. Add type hints
19. Add docstrings (at minimum on public APIs)
20. Write tests
21. Set up CI/CD pipeline
22. Clean up commented-out code
23. Resolve single vs dual requirements.txt
24. Add proper API documentation (drf-spectacular or drf-yasg)
