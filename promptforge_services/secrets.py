from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken


DEFAULT_SECRET_KEY_VERSION = 1


class SecretsEncryptionError(RuntimeError):
    pass


@dataclass(frozen=True)
class EncryptedSecret:
    ciphertext: str
    key_version: int = DEFAULT_SECRET_KEY_VERSION


def _master_key() -> str | None:
    value = os.getenv("PROMPTFORGE_SECRETS_MASTER_KEY")
    if value is None:
        return None
    text = value.strip()
    return text or None


def secrets_encryption_available() -> bool:
    return _master_key() is not None


def current_secret_key_version() -> int:
    raw = os.getenv("PROMPTFORGE_SECRETS_KEY_VERSION", str(DEFAULT_SECRET_KEY_VERSION)).strip()
    try:
        parsed = int(raw)
    except ValueError as exc:
        raise SecretsEncryptionError("invalid_secret_key_version") from exc
    if parsed < 1:
        raise SecretsEncryptionError("invalid_secret_key_version")
    return parsed


def _fernet() -> Fernet:
    master_key = _master_key()
    if master_key is None:
        raise SecretsEncryptionError("secrets_encryption_unconfigured")
    try:
        key_bytes = master_key.encode("utf-8")
        # Validate key format up front.
        base64.urlsafe_b64decode(key_bytes)
        return Fernet(key_bytes)
    except Exception as exc:
        raise SecretsEncryptionError("invalid_secrets_master_key") from exc


def encrypt_secret(secret_value: str) -> EncryptedSecret:
    token = _fernet().encrypt(secret_value.encode("utf-8")).decode("utf-8")
    return EncryptedSecret(ciphertext=token, key_version=current_secret_key_version())


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise SecretsEncryptionError("secret_decryption_failed") from exc
