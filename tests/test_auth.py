import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from app.auth import validate_init_data

TOKEN = "123:TEST"


def sign(fields: dict, token: str = TOKEN) -> str:
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    return urlencode({**fields, "hash": hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()})


def make(user_id: int = 42, age: int = 0, token: str = TOKEN) -> str:
    return sign({"auth_date": str(int(time.time()) - age), "user": json.dumps({"id": user_id, "first_name": "A"})}, token)


def test_valid():
    assert validate_init_data(make(), TOKEN)["id"] == 42


def test_wrong_token():
    assert validate_init_data(make(token="999:OTHER"), TOKEN) is None


def test_tampered():
    assert validate_init_data(make().replace("%22id%22%3A+42", "%22id%22%3A+1"), TOKEN) is None


def test_expired():
    assert validate_init_data(make(age=3 * 24 * 3600), TOKEN) is None


def test_garbage():
    assert validate_init_data("nonsense", TOKEN) is None
