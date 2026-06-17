"""Application-level envelope encryption.

Scheme (KEK -> DEK):
  * A long-lived master Key-Encryption-Key (KEK) is supplied out-of-band
    (env in dev, KMS/CMEK in production). It is never persisted by the app.
  * Each ``encrypt`` call generates a fresh random Data-Encryption-Key (DEK),
    encrypts the plaintext with AES-256-GCM under the DEK, then wraps (encrypts)
    the DEK with the KEK (also AES-256-GCM). Only the wrapped DEK + ciphertext +
    nonces are stored.
  * A ``key_version`` is recorded with every blob so the KEK can be rotated later
    without breaking old data (decrypt selects the KEK for the stored version).

Why AES-GCM: it is an AEAD cipher — it provides confidentiality AND integrity, so
any tampering with the ciphertext (or the wrapped DEK) is detected on decrypt and
raises rather than returning corrupt/forged plaintext.

This module is intentionally provider-agnostic: swapping ``MASTER_KEK`` for a KMS
call later requires changing only ``_kek_for_version`` — the on-disk blob format and
all call sites stay the same.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

# GCM standard nonce size (96 bits) and AES-256 key size (32 bytes).
_NONCE_SIZE = 12
_KEY_SIZE = 32


class EncryptionError(Exception):
    """Raised when encryption or decryption fails (including tamper detection)."""


@dataclass(frozen=True)
class EncryptedBlob:
    """An encrypted value plus everything needed to decrypt it (except the KEK)."""

    ciphertext: bytes
    nonce: bytes
    wrapped_dek: bytes
    dek_nonce: bytes
    key_version: int

    def to_token(self) -> str:
        """Serialize to a compact, storable base64 JSON token."""
        payload = {
            "v": self.key_version,
            "ct": base64.b64encode(self.ciphertext).decode(),
            "n": base64.b64encode(self.nonce).decode(),
            "wdek": base64.b64encode(self.wrapped_dek).decode(),
            "dn": base64.b64encode(self.dek_nonce).decode(),
        }
        return base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()

    @classmethod
    def from_token(cls, token: str) -> EncryptedBlob:
        try:
            payload = json.loads(base64.b64decode(token))
            return cls(
                ciphertext=base64.b64decode(payload["ct"]),
                nonce=base64.b64decode(payload["n"]),
                wrapped_dek=base64.b64decode(payload["wdek"]),
                dek_nonce=base64.b64decode(payload["dn"]),
                key_version=int(payload["v"]),
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise EncryptionError("Malformed encrypted token.") from exc


def _kek_for_version(key_version: int) -> bytes:
    """Return the master KEK bytes for a given key version.

    Phase 0 supports a single active version. When rotation is introduced, this is
    the single place that maps version -> key material (e.g. via a KMS lookup).
    """
    if key_version != settings.ENCRYPTION_KEY_VERSION:
        raise EncryptionError(
            f"No key material configured for key_version={key_version}."
        )
    return settings.master_kek_bytes


def encrypt(plaintext: bytes, *, key_version: int | None = None) -> EncryptedBlob:
    """Encrypt ``plaintext`` using a fresh DEK wrapped by the master KEK."""
    version = settings.ENCRYPTION_KEY_VERSION if key_version is None else key_version
    kek = _kek_for_version(version)

    dek = AESGCM.generate_key(bit_length=_KEY_SIZE * 8)

    data_nonce = _random_nonce()
    ciphertext = AESGCM(dek).encrypt(data_nonce, plaintext, None)

    dek_nonce = _random_nonce()
    wrapped_dek = AESGCM(kek).encrypt(dek_nonce, dek, None)

    return EncryptedBlob(
        ciphertext=ciphertext,
        nonce=data_nonce,
        wrapped_dek=wrapped_dek,
        dek_nonce=dek_nonce,
        key_version=version,
    )


def decrypt(blob: EncryptedBlob) -> bytes:
    """Decrypt an :class:`EncryptedBlob`. Raises EncryptionError on any tampering."""
    kek = _kek_for_version(blob.key_version)
    try:
        dek = AESGCM(kek).decrypt(blob.dek_nonce, blob.wrapped_dek, None)
        if len(dek) != _KEY_SIZE:
            raise EncryptionError("Unwrapped DEK has unexpected length.")
        return AESGCM(dek).decrypt(blob.nonce, blob.ciphertext, None)
    except EncryptionError:
        raise
    except Exception as exc:  # cryptography raises InvalidTag on tamper/wrong key
        raise EncryptionError("Decryption failed (wrong key or tampered data).") from exc


def encrypt_str(plaintext: str, *, key_version: int | None = None) -> str:
    """Convenience: encrypt a string and return a storable token."""
    return encrypt(plaintext.encode("utf-8"), key_version=key_version).to_token()


def decrypt_str(token: str) -> str:
    """Convenience: decrypt a token produced by :func:`encrypt_str`."""
    return decrypt(EncryptedBlob.from_token(token)).decode("utf-8")


def _random_nonce() -> bytes:
    import os

    return os.urandom(_NONCE_SIZE)
