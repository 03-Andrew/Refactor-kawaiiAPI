from .base import *

CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:5174",  # Add your frontend URL here
    "https://kawaii-project-front-sw7d.vercel.app",
    "https://kawaii-booking-front.vercel.app",
]
CORS_ALLOW_CREDENTIALS = True