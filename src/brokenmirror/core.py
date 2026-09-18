import base64
import json
import os
import secrets
import shutil
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

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


def clean_directory_except_git(target_dir: Path):
    """Curata fisierele si folderele dintr-un director, pastrand intact folderul .git."""
    if not target_dir.exists():
        target_dir.mkdir(parents=True, exist_ok=True)
        return

    for item in target_dir.iterdir():
        if item.name == ".git":
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()


def encrypt_payload(aes: AESGCM, data: bytes) -> bytes:
    nonce = secrets.token_bytes(12)
    return nonce + aes.encrypt(nonce, data, None)


def decrypt_payload(aes: AESGCM, payload: bytes) -> bytes:
    nonce = payload[:12]
    ciphertext = payload[12:]
    return aes.decrypt(nonce, ciphertext, None)


def obfuscate_repository(
    src_dir: str, out_dir: str, matrix_path: str, num_buckets: int = 8
) -> tuple[str, int]:
    src = Path(src_dir).resolve()
    out = Path(out_dir).resolve()
    matrix_file = Path(matrix_path).resolve()

    # Curatam destinația fara sa stergem repo-ul .git existent
    clean_directory_except_git(out)

    # Asiguram existenta folderului pentru cheie/matrice
    matrix_file.parent.mkdir(parents=True, exist_ok=True)

    key = AESGCM.generate_key(bit_length=256)
    aes = AESGCM(key)

    # Generare bucket-uri si .gitkeep in fiecare
    buckets = [f"d_{secrets.token_hex(4)}" for _ in range(max(1, num_buckets))]
    for b in buckets:
        bucket_path = out / b
        bucket_path.mkdir(parents=True, exist_ok=True)
        (bucket_path / ".gitkeep").touch(exist_ok=True)

    path_matrix = {}
    processed_count = 0

    for root, dirs, files in os.walk(src):
        # Excludem .git si folderele ignorate din parcurgere
        dirs[:] = [d for d in dirs if d not in IGNORED_NAMES]
        rel_root = Path(root).relative_to(src)

        for file_name in files:
            if file_name in IGNORED_NAMES:
                continue

            orig_rel = rel_root / file_name
            orig_full = src / orig_rel

            bucket = secrets.choice(buckets)
            anon_name = f"f_{secrets.token_hex(8)}.bin"
            anon_rel = Path(bucket) / anon_name
            anon_full = out / anon_rel

            raw_bytes = orig_full.read_bytes()
            encrypted_data = encrypt_payload(aes, raw_bytes)
            anon_full.write_bytes(encrypted_data)

            path_matrix[str(anon_rel).replace("\\", "/")] = str(
                orig_rel
            ).replace("\\", "/")
            processed_count += 1

    matrix_bytes = json.dumps(
        {"version": 1, "map": path_matrix}, indent=2
    ).encode("utf-8")
    encrypted_matrix = encrypt_payload(aes, matrix_bytes)
    matrix_file.write_bytes(encrypted_matrix)

    key_b64 = base64.b64encode(key).decode("utf-8")
    return key_b64, processed_count


def restore_repository(
    obf_dir: str, restore_dir: str, matrix_path: str, key_b64: str
) -> int:
    obf = Path(obf_dir).resolve()
    target = Path(restore_dir).resolve()
    matrix_file = Path(matrix_path).resolve()

    # Curatam destinația de restore pastrand .git intact daca exista deja
    clean_directory_except_git(target)

    key = base64.b64decode(key_b64)
    aes = AESGCM(key)

    encrypted_matrix = matrix_file.read_bytes()
    matrix_raw = decrypt_payload(aes, encrypted_matrix).decode("utf-8")
    mapping = json.loads(matrix_raw)["map"]

    restored_count = 0
    for anon_rel, orig_rel in mapping.items():
        anon_file = obf / Path(anon_rel)
        dest_file = target / Path(orig_rel)

        if not anon_file.exists():
            continue

        dest_file.parent.mkdir(parents=True, exist_ok=True)
        decrypted_data = decrypt_payload(aes, anon_file.read_bytes())
        dest_file.write_bytes(decrypted_data)
        restored_count += 1

    return restored_count