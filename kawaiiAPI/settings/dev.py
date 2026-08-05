from .base import *
load_dotenv()
import dj_database_url

DEBUG = True
ALLOWED_HOSTS = ['*']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
        # dj_database_url.parse(
        #     os.getenv('DATABASE_URL'),
        #     conn_max_age=600,       # Keep database connections open briefly for performance
        #     conn_health_checks=True # Auto-reconnect if a connection drops
        # )
    
}

CORS_ALLOW_ALL_ORIGINS = True