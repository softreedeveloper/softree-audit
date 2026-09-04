"""Hash de contraseñas con Argon2id (`docs/spec/security.md` §4)."""

from __future__ import annotations

import time

import pytest
from softree_audit.core.security import (
    hash_password,
    needs_rehash,
    verify_password,
    waste_time_like_verification,
)

pytestmark = pytest.mark.unit

PASSWORD = "una-contrasena-suficientemente-larga"


def test_hash_is_argon2id() -> None:
    digest = hash_password(PASSWORD)
    assert digest.startswith("$argon2id$")


def test_hash_is_salted_per_call() -> None:
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_verify_accepts_correct_password() -> None:
    assert verify_password(PASSWORD, hash_password(PASSWORD)) is True


def test_verify_rejects_wrong_password() -> None:
    assert verify_password("otra-cosa-completamente", hash_password(PASSWORD)) is False


def test_verify_rejects_malformed_hash() -> None:
    """Un hash corrupto en base de datos no debe provocar una excepción."""
    assert verify_password(PASSWORD, "no-es-un-hash") is False


def test_password_is_never_stored_in_the_hash() -> None:
    assert PASSWORD not in hash_password(PASSWORD)


def test_current_parameters_do_not_need_rehash() -> None:
    assert needs_rehash(hash_password(PASSWORD)) is False


def test_unknown_hash_format_needs_rehash() -> None:
    assert needs_rehash("$2b$12$algoquenoesargon") is True


@pytest.mark.security
def test_decoy_verification_takes_comparable_time() -> None:
    """El camino de «usuario inexistente» debe costar lo mismo que el real.

    Evita distinguir por latencia si un email existe (enumeración de usuarios).
    """
    digest = hash_password(PASSWORD)

    start = time.perf_counter()
    verify_password("incorrecta-pero-plausible", digest)
    real = time.perf_counter() - start

    start = time.perf_counter()
    waste_time_like_verification()
    decoy = time.perf_counter() - start

    # Umbral amplio: la comparación es de orden de magnitud, no de precisión.
    assert 0.2 < decoy / real < 5.0
