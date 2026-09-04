"""Cifrado en reposo de credenciales de terceros (`security.md` §7)."""

from __future__ import annotations

import pytest
from softree_audit.core.crypto import DecryptionError, SecretBox

pytestmark = pytest.mark.unit

KEY = "clave-actual-suficientemente-larga-0123456789"
OLD_KEY = "clave-anterior-suficientemente-larga-9876543"
TOKEN = "1//04refresh-token-de-google-de-ejemplo"


def test_round_trip() -> None:
    box = SecretBox(KEY)
    assert box.decrypt(box.encrypt(TOKEN)) == TOKEN


def test_ciphertext_does_not_contain_plaintext() -> None:
    ciphertext = SecretBox(KEY).encrypt(TOKEN)
    assert TOKEN.encode() not in ciphertext


def test_ciphertext_differs_between_calls() -> None:
    box = SecretBox(KEY)
    assert box.encrypt(TOKEN) != box.encrypt(TOKEN)


def test_another_key_cannot_decrypt() -> None:
    ciphertext = SecretBox(KEY).encrypt(TOKEN)
    with pytest.raises(DecryptionError):
        SecretBox(OLD_KEY).decrypt(ciphertext)


def test_previous_key_is_accepted_during_rotation() -> None:
    ciphertext = SecretBox(OLD_KEY).encrypt(TOKEN)
    rotating = SecretBox(KEY, OLD_KEY)
    assert rotating.decrypt(ciphertext) == TOKEN


def test_rotate_reencrypts_with_the_current_key() -> None:
    ciphertext = SecretBox(OLD_KEY).encrypt(TOKEN)
    rotated = SecretBox(KEY, OLD_KEY).rotate(ciphertext)
    # Tras rotar, la clave nueva basta por sí sola.
    assert SecretBox(KEY).decrypt(rotated) == TOKEN


def test_corrupted_ciphertext_raises_domain_error() -> None:
    with pytest.raises(DecryptionError):
        SecretBox(KEY).decrypt(b"esto-no-es-un-token-fernet")


def test_error_message_never_leaks_the_ciphertext() -> None:
    ciphertext = SecretBox(OLD_KEY).encrypt(TOKEN)
    with pytest.raises(DecryptionError) as excinfo:
        SecretBox(KEY).decrypt(ciphertext)
    assert ciphertext.decode() not in str(excinfo.value)
