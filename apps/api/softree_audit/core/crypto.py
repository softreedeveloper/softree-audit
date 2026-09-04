"""Cifrado en reposo de credenciales de terceros.

Se usa para los refresh tokens de Google (`docs/spec/security.md` §7). La clave
se deriva de `SECRET_KEY` con HKDF-SHA256, de modo que no exista un secreto
adicional que gestionar en el MVP.
"""

from __future__ import annotations

import base64

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

HKDF_INFO = b"softree-audit/oauth/v1"


class DecryptionError(Exception):
    """El texto cifrado no pudo descifrarse con ninguna clave disponible."""


def _derive_key(secret_key: str) -> bytes:
    kdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=HKDF_INFO)
    return base64.urlsafe_b64encode(kdf.derive(secret_key.encode("utf-8")))


class SecretBox:
    """Cifra y descifra credenciales.

    Acepta una clave anterior para permitir la rotación descrita en
    `docs/development/deployment.md`: se descifra con cualquiera de las dos y se
    cifra siempre con la actual.
    """

    def __init__(self, secret_key: str, previous_secret_key: str | None = None) -> None:
        keys = [Fernet(_derive_key(secret_key))]
        if previous_secret_key:
            keys.append(Fernet(_derive_key(previous_secret_key)))
        self._fernet = MultiFernet(keys)

    def encrypt(self, plaintext: str) -> bytes:
        return self._fernet.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, ciphertext: bytes) -> str:
        try:
            return self._fernet.decrypt(ciphertext).decode("utf-8")
        except InvalidToken as exc:
            # No se incluye el ciphertext en el mensaje: nunca debe llegar a un log.
            raise DecryptionError("No fue posible descifrar la credencial almacenada") from exc

    def rotate(self, ciphertext: bytes) -> bytes:
        """Recifra con la clave actual sin exponer el texto en claro."""
        try:
            return self._fernet.rotate(ciphertext)
        except InvalidToken as exc:
            raise DecryptionError("No fue posible recifrar la credencial almacenada") from exc
