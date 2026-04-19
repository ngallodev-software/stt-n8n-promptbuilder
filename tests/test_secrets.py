from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from promptforge_services.secrets import (
    SecretsEncryptionError,
    current_secret_key_version,
    decrypt_secret,
    encrypt_secret,
)


def test_secret_encrypt_decrypt_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROMPTFORGE_SECRETS_MASTER_KEY", Fernet.generate_key().decode("utf-8"))
    monkeypatch.setenv("PROMPTFORGE_SECRETS_KEY_VERSION", "3")

    encrypted = encrypt_secret("super-secret")

    assert encrypted.ciphertext != "super-secret"
    assert encrypted.key_version == 3
    assert decrypt_secret(encrypted.ciphertext) == "super-secret"


def test_secret_key_version_rejects_invalid_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROMPTFORGE_SECRETS_MASTER_KEY", Fernet.generate_key().decode("utf-8"))
    monkeypatch.setenv("PROMPTFORGE_SECRETS_KEY_VERSION", "0")

    with pytest.raises(SecretsEncryptionError, match="invalid_secret_key_version"):
        current_secret_key_version()


def test_secret_decrypt_fails_with_wrong_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROMPTFORGE_SECRETS_MASTER_KEY", Fernet.generate_key().decode("utf-8"))
    encrypted = encrypt_secret("super-secret")
    monkeypatch.setenv("PROMPTFORGE_SECRETS_MASTER_KEY", Fernet.generate_key().decode("utf-8"))

    with pytest.raises(SecretsEncryptionError, match="secret_decryption_failed"):
        decrypt_secret(encrypted.ciphertext)
