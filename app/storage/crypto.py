import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_SIZE = 12


class EncryptionKeyMissing(Exception):
    """Raised when TOKEN_ENCRYPTION_KEY is not set."""


def encrypt(plaintext: str, key_material: str) -> bytes:
    aesgcm = AESGCM(_derive_key(key_material))
    nonce = os.urandom(_NONCE_SIZE)
    return nonce + aesgcm.encrypt(nonce, plaintext.encode(), None)


def decrypt(payload: bytes, key_material: str) -> str:
    if len(payload) <= _NONCE_SIZE:
        raise ValueError("Encrypted payload is too short")
    nonce, ciphertext = payload[:_NONCE_SIZE], payload[_NONCE_SIZE:]
    aesgcm = AESGCM(_derive_key(key_material))
    return aesgcm.decrypt(nonce, ciphertext, None).decode()


def _derive_key(key_material: str) -> bytes:
    if not key_material:
        raise EncryptionKeyMissing
    return hashlib.sha256(key_material.encode()).digest()
