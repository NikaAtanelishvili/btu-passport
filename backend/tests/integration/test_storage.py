"""BE-22: content-addressed object storage in the test bucket."""

import hashlib
import os

from app.services import storage


def test_put_then_get(s3_bucket: str) -> None:
    data = os.urandom(64)
    key = storage.pdf_key(hashlib.sha256(data).hexdigest())
    assert key.startswith("pdf/") and key.endswith(".pdf") and len(key) == 4 + 64 + 4
    storage.put(key, data, "application/pdf")
    assert storage.exists(key)
    assert storage.get(key) == data


def test_put_never_overwrites_an_existing_key(s3_bucket: str) -> None:
    data = os.urandom(64)
    key = storage.pdf_key(hashlib.sha256(data).hexdigest())
    storage.put(key, data, "application/pdf")
    storage.put(key, b"something else", "application/pdf")
    assert storage.get(key) == data
