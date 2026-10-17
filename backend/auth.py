import hashlib
import hmac
import secrets
import time


def password_hash(password):
    salt = secrets.token_hex(16)
    result = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return salt + ':' + result


def check_password(password, hashed):
    salt, expected = hashed.split(':', 1)
    actual = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return hmac.compare_digest(actual, expected)


def token_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def create_session(store, user):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    store.put('sessions', {'id': token_hash(token), 'user_id': user['id'], 'csrf': csrf, 'expires': time.time() + 8 * 3600})
    return token, csrf
