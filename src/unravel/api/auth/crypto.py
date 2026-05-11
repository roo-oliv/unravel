"""Symmetric encryption for at-rest secrets (GitHub OAuth tokens).

Phase 1 keys off ``SESSION_SECRET``. Phase 2 will plug a real KMS (AWS KMS or
External Secrets Operator) and rotation, with this module as the only seam.

Note on rotation: changing ``SESSION_SECRET`` makes every stored token
undecryptable. When we add rotation, switch to a versioned envelope (``v1:...``)
that can hold multiple decryption keys.
"""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken


class TokenCryptoError(RuntimeError):
    """Raised when an at-rest token can't be encrypted or decrypted."""


def _fernet() -> Fernet:
    secret = os.environ.get("SESSION_SECRET", "").strip()
    if not secret or secret == "dev-only-change-me":
        # We refuse to encrypt with the placeholder so an unconfigured prod
        # instance fails loudly instead of silently writing tokens under a
        # known key.
        raise TokenCryptoError(
            "SESSION_SECRET is not set (or still the dev placeholder). "
            "Generate one with: "
            'python -c "import secrets; print(secrets.token_urlsafe(32))"'
        )
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    """Encrypt a UTF-8 string. Returns a base64-urlsafe Fernet token (str)."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a Fernet token back to the original UTF-8 string."""
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise TokenCryptoError(
            "Failed to decrypt at-rest secret — SESSION_SECRET likely changed."
        ) from exc
