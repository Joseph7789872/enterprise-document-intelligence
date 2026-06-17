"""Tests for the envelope encryption service."""

from __future__ import annotations

import dataclasses

import pytest
from app.core.crypto import (
    EncryptedBlob,
    EncryptionError,
    decrypt,
    decrypt_str,
    encrypt,
    encrypt_str,
)


def test_round_trip_bytes() -> None:
    plaintext = b"attorney-client privileged content"
    blob = encrypt(plaintext)
    assert blob.ciphertext != plaintext
    assert decrypt(blob) == plaintext


def test_round_trip_str_via_token() -> None:
    token = encrypt_str("confidential matter notes")
    assert isinstance(token, str)
    assert decrypt_str(token) == "confidential matter notes"


def test_unique_dek_and_nonce_per_call() -> None:
    a = encrypt(b"same plaintext")
    b = encrypt(b"same plaintext")
    # Fresh DEK + nonce each time → ciphertext and wrapped DEK differ.
    assert a.ciphertext != b.ciphertext
    assert a.wrapped_dek != b.wrapped_dek
    assert a.nonce != b.nonce


def test_key_version_preserved() -> None:
    blob = encrypt(b"data")
    token = blob.to_token()
    restored = EncryptedBlob.from_token(token)
    assert restored.key_version == blob.key_version
    assert decrypt(restored) == b"data"


def test_tampered_ciphertext_is_rejected() -> None:
    blob = encrypt(b"sensitive")
    tampered = dataclasses.replace(blob, ciphertext=blob.ciphertext[:-1] + bytes([blob.ciphertext[-1] ^ 0x01]))
    with pytest.raises(EncryptionError):
        decrypt(tampered)


def test_tampered_wrapped_dek_is_rejected() -> None:
    blob = encrypt(b"sensitive")
    tampered = dataclasses.replace(
        blob, wrapped_dek=blob.wrapped_dek[:-1] + bytes([blob.wrapped_dek[-1] ^ 0x01])
    )
    with pytest.raises(EncryptionError):
        decrypt(tampered)


def test_unknown_key_version_is_rejected() -> None:
    blob = encrypt(b"data")
    bad = dataclasses.replace(blob, key_version=999)
    with pytest.raises(EncryptionError):
        decrypt(bad)


def test_malformed_token_is_rejected() -> None:
    with pytest.raises(EncryptionError):
        EncryptedBlob.from_token("not-a-valid-token")
