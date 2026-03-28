from __future__ import annotations

from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


KEY_DIR = Path(__file__).resolve().parents[2] / ".secrets"
PRIVATE_KEY_PATH = KEY_DIR / "mx_rsa_private.pem"
PUBLIC_KEY_PATH = KEY_DIR / "mx_rsa_public.pem"


def ensure_rsa_keys() -> None:
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    if PRIVATE_KEY_PATH.exists() and PUBLIC_KEY_PATH.exists():
        return
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    PRIVATE_KEY_PATH.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    PUBLIC_KEY_PATH.write_bytes(
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )


def _load_private_key():
    ensure_rsa_keys()
    return serialization.load_pem_private_key(PRIVATE_KEY_PATH.read_bytes(), password=None)


def _load_public_key():
    ensure_rsa_keys()
    return serialization.load_pem_public_key(PUBLIC_KEY_PATH.read_bytes())


def encrypt_text(value: str) -> str:
    encrypted = _load_public_key().encrypt(
        value.encode("utf-8"),
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    return encrypted.hex()


def decrypt_text(value: str) -> str:
    decrypted = _load_private_key().decrypt(
        bytes.fromhex(value),
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    return decrypted.decode("utf-8")
