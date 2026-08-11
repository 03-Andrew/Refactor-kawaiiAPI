import requests
from kawaiiAPI.settings.base import TURNSTILE_SECRET_KEY


def validate_turnstile(token, remoteip=None):
    url = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'
    data = {
        'secret': TURNSTILE_SECRET_KEY,
        'response': token.strip() if token else '',
    }

    if remoteip:
        data['remoteip'] = remoteip
    try:
        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'error-codes': ['internal-error']}