import base64
import hashlib
import hmac
import json
import secrets
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.keywrap import aes_key_wrap, aes_key_unwrap

IGNORED_NAMES = {
    ".git",
    ".idea",
    ".vscode",
    "__pycache__",
    ".venv",
    "node_modules",
    "dist",
    "build",
}


def get_deterministic_paths(
    rel_path_str: str, dek_bytes: bytes, num_buckets: int = 8
) -> tuple[str, str]:
    """Derives a deterministic bucket directory and binary filename from relative path and DEK."""
    norm_path = rel_path_str.replace("\\", "/").strip("/")
    digest = hmac.new(dek_bytes, norm_path.encode("utf-8"), hashlib.sha256).hexdigest()

    bucket_index = int(digest[:8], 16) % max(1, num_buckets)
    bucket_name = f"d_{bucket_index:04x}"
    anon_file = f"f_{digest[8:24]}.bin"
    anon_rel = f"{bucket_name}/{anon_file}"
    return bucket_name, anon_rel


def encrypt_payload(aes: AESGCM, data: bytes) -> bytes:
    """Encrypts raw bytes using AES-256-GCM with a prepended 12-byte nonce."""
    nonce = secrets.token_bytes(12)
    return nonce + aes.encrypt(nonce, data, None)


def decrypt_payload(aes: AESGCM, payload: bytes) -> bytes:
    """Decrypts payload by extracting the leading 12-byte nonce and decrypting ciphertext."""
    nonce = payload[:12]
    ciphertext = payload[12:]
    return aes.decrypt(nonce, ciphertext, None)


def init_dual_envelope_matrix(
    matrix_path: Path, user_key_b64: str, backup_key_b64: str
) -> bytes:
    """Generates a DEK and wraps it inside user and backup envelopes."""
    dek = AESGCM.generate_key(bit_length=256)
    user_kek = base64.b64decode(user_key_b64)
    backup_kek = base64.b64decode(backup_key_b64)

    wrapped_user = aes_key_wrap(user_kek, dek)
    wrapped_backup = aes_key_wrap(backup_kek, dek)

    aes_dek = AESGCM(dek)
    empty_map_payload = json.dumps({"version": 2, "map": {}}).encode("utf-8")
    enc_map = encrypt_payload(aes_dek, empty_map_payload)

    matrix_data = {
        "version": 2,
        "envelopes": {
            "user": base64.b64encode(wrapped_user).decode("ascii"),
            "backup": base64.b64encode(wrapped_backup).decode("ascii"),
        },
        "payload": base64.b64encode(enc_map).decode("ascii"),
    }

    matrix_path.parent.mkdir(parents=True, exist_ok=True)
    matrix_path.write_text(json.dumps(matrix_data, indent=2))
    return dek


def unlock_dek_from_matrix(matrix_path: Path, candidate_key_b64: str) -> tuple[bytes, dict]:
    """Unlocks the DEK using either the user key or the backup recovery key."""
    matrix_info = json.loads(matrix_path.read_text())
    candidate_kek = base64.b64decode(candidate_key_b64)

    user_wrap = base64.b64decode(matrix_info["envelopes"]["user"])
    backup_wrap = base64.b64decode(matrix_info["envelopes"]["backup"])

    dek = None
    try:
        dek = aes_key_unwrap(candidate_kek, user_wrap)
    except Exception:
        pass

    if dek is None:
        try:
            dek = aes_key_unwrap(candidate_kek, backup_wrap)
        except Exception:
            pass

    if dek is None:
        raise ValueError("Provided key could not unlock either user or backup key slots.")

    aes_dek = AESGCM(dek)
    enc_payload = base64.b64decode(matrix_info["payload"])
    decrypted_bytes = decrypt_payload(aes_dek, enc_payload)
    mapping = json.loads(decrypted_bytes.decode("utf-8")).get("map", {})

    return dek, mapping


def save_matrix_payload(matrix_path: Path, dek: bytes, mapping: dict):
    """Encrypts mapping with DEK and updates the envelope container on disk."""
    matrix_info = json.loads(matrix_path.read_text())
    aes_dek = AESGCM(dek)
    payload_raw = json.dumps({"version": 2, "map": mapping}, indent=2).encode("utf-8")
    enc_payload = encrypt_payload(aes_dek, payload_raw)
    matrix_info["payload"] = base64.b64encode(enc_payload).decode("ascii")
    matrix_path.write_text(json.dumps(matrix_info, indent=2))