from cryptography.fernet import Fernet
from django.conf import settings


def _fernet() -> Fernet:
    key = settings.SUPPORT_CHAT_KEY
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


def encrypt_message(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_message(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()
