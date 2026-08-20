from __future__ import annotations

import argparse
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt


MAGIC = b"PLOTLOT-AEAD-V1\x00"
SALT_BYTES = 16
NONCE_BYTES = 12


def encrypt(content: bytes, passphrase: str) -> bytes:
    salt = os.urandom(SALT_BYTES)
    nonce = os.urandom(NONCE_BYTES)
    key = _derive_key(passphrase, salt)
    return MAGIC + salt + nonce + AESGCM(key).encrypt(nonce, content, MAGIC)


def decrypt(content: bytes, passphrase: str) -> bytes:
    header_size = len(MAGIC) + SALT_BYTES + NONCE_BYTES
    if len(content) <= header_size or not content.startswith(MAGIC):
        raise RuntimeError("invalid authenticated backup envelope")
    salt_start = len(MAGIC)
    nonce_start = salt_start + SALT_BYTES
    salt = content[salt_start:nonce_start]
    nonce = content[nonce_start:header_size]
    key = _derive_key(passphrase, salt)
    return AESGCM(key).decrypt(nonce, content[header_size:], MAGIC)


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    if len(passphrase) < 12:
        raise ValueError("backup passphrase must be at least 12 characters")
    return Scrypt(salt=salt, length=32, n=2**14, r=8, p=1).derive(passphrase.encode())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("encrypt", "decrypt"))
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    arguments = parser.parse_args()
    source = arguments.source.read_bytes()
    passphrase = os.environ["STORAGE_BACKUP_PASSPHRASE"]
    result = (
        encrypt(source, passphrase)
        if arguments.command == "encrypt"
        else decrypt(source, passphrase)
    )
    arguments.destination.write_bytes(result)


if __name__ == "__main__":
    main()
