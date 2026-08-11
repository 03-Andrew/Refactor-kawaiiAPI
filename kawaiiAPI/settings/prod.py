from .base import *

DEBUG = os.environ.get("DEBUG", "False").lower() == "true"

CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "test-booking.dreww.space").split(",")

CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:5174",  # Add your frontend URL here
    "https://kawaii-project-front-sw7d.vercel.app",
    "https://kawaii-booking-front.vercel.app",
]
CORS_ALLOW_CREDENTIALS = True