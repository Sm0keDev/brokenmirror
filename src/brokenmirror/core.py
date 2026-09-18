import base64
import hashlib
import hmac
import json
import os
import secrets
import shutil
import time
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


def get_deterministic_paths(
    rel_path_str: str, key_bytes: bytes, num_buckets: int = 8
) -> tuple[str, str]:
    """Derives a deterministic bucket directory and binary filename from the relative path and key."""
    norm_path = rel_path_str.replace("\\", "/").strip("/")
    digest = hmac.new(key_bytes, norm_path.encode("utf-8"), hashlib.sha256).hexdigest()

    bucket_index = int(digest[:8], 16) % max(1, num_buckets)
    bucket_name = f"d_{bucket_index:04x}"
    anon_file = f"f_{digest[8:24]}.bin"
    anon_rel = f"{bucket_name}/{anon_file}"
    return bucket_name, anon_rel


def clean_directory_except_git(target_dir: Path):
    """Removes all files and subdirectories within target_dir, keeping the .git directory intact."""
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
    """Encrypts raw bytes using AES-256-GCM with a prepended 12-byte nonce."""
    nonce = secrets.token_bytes(12)
    return nonce + aes.encrypt(nonce, data, None)


def decrypt_payload(aes: AESGCM, payload: bytes) -> bytes:
    """Decrypts payload by extracting the leading 12-byte nonce and decrypting the remaining ciphertext."""
    nonce = payload[:12]
    ciphertext = payload[12:]
    return aes.decrypt(nonce, ciphertext, None)


def load_or_create_matrix(matrix_path: Path, aes: AESGCM) -> dict:
    """Loads and decrypts the path matrix file if it exists, otherwise returns an empty dictionary."""
    if matrix_path.exists():
        try:
            decrypted = decrypt_payload(aes, matrix_path.read_bytes())
            return json.loads(decrypted.decode("utf-8")).get("map", {})
        except Exception:
            return {}
    return {}


def save_matrix(matrix_path: Path, aes: AESGCM, mapping: dict):
    """Encrypts and writes the updated path mapping matrix to disk."""
    payload = json.dumps({"version": 1, "map": mapping}, indent=2).encode("utf-8")
    matrix_path.parent.mkdir(parents=True, exist_ok=True)
    matrix_path.write_bytes(encrypt_payload(aes, payload))


def obfuscate_single_file(
    src_full: Path,
    rel_path: str,
    out_dir: Path,
    key_bytes: bytes,
    aes: AESGCM,
    num_buckets: int = 8,
) -> str:
    """Encrypts a single file and places it into its deterministic bucket location."""
    bucket_name, anon_rel = get_deterministic_paths(rel_path, key_bytes, num_buckets)
    bucket_path = out_dir / bucket_name
    bucket_path.mkdir(parents=True, exist_ok=True)
    (bucket_path / ".gitkeep").touch(exist_ok=True)

    anon_full = out_dir / Path(anon_rel)
    raw_data = src_full.read_bytes()
    anon_full.write_bytes(encrypt_payload(aes, raw_data))
    return anon_rel


def obfuscate_repository(
    src_dir: str,
    out_dir: str,
    matrix_path: str,
    key_b64: str | None = None,
    num_buckets: int = 8,
) -> tuple[str, int]:
    """Obfuscates an entire repository into encrypted buckets while maintaining .git in the destination."""
    src = Path(src_dir).resolve()
    out = Path(out_dir).resolve()
    matrix_file = Path(matrix_path).resolve()

    clean_directory_except_git(out)

    if key_b64:
        key = base64.b64decode(key_b64)
    else:
        key = AESGCM.generate_key(bit_length=256)

    aes = AESGCM(key)
    path_matrix = {}
    processed_count = 0

    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in IGNORED_NAMES]
        rel_root = Path(root).relative_to(src)

        for file_name in files:
            if file_name in IGNORED_NAMES:
                continue

            orig_rel = str(rel_root / file_name).replace("\\", "/")
            orig_full = src / orig_rel

            anon_rel = obfuscate_single_file(
                orig_full, orig_rel, out, key, aes, num_buckets
            )
            path_matrix[anon_rel] = orig_rel
            processed_count += 1

    save_matrix(matrix_file, aes, path_matrix)
    return base64.b64encode(key).decode("utf-8"), processed_count


def restore_repository(
    obf_dir: str, restore_dir: str, matrix_path: str, key_b64: str
) -> int:
    """Reconstructs the original repository structure and files from the encrypted repository."""
    obf = Path(obf_dir).resolve()
    target = Path(restore_dir).resolve()
    matrix_file = Path(matrix_path).resolve()

    clean_directory_except_git(target)

    key = base64.b64decode(key_b64)
    aes = AESGCM(key)

    mapping = load_or_create_matrix(matrix_file, aes)
    restored_count = 0

    for anon_rel, orig_rel in mapping.items():
        anon_file = obf / Path(anon_rel)
        dest_file = target / Path(orig_rel)

        if not anon_file.exists():
            continue

        dest_file.parent.mkdir(parents=True, exist_ok=True)
        dest_file.write_bytes(decrypt_payload(aes, anon_file.read_bytes()))
        restored_count += 1

    return restored_count


def watch_repository(
    src_dir: str,
    out_dir: str,
    matrix_path: str,
    key_b64: str,
    num_buckets: int = 8,
    interval: float = 1.0,
):
    """Watches the source directory for changes and continuously updates the encrypted repository."""
    src = Path(src_dir).resolve()
    out = Path(out_dir).resolve()
    matrix_file = Path(matrix_path).resolve()

    key = base64.b64decode(key_b64)
    aes = AESGCM(key)

    mapping = load_or_create_matrix(matrix_file, aes)
    rev_mapping = {v: k for k, v in mapping.items()}
    snapshot = {}

    print(f"[*] Watcher active on: {src}")
    print(f"[*] Encrypted target: {out}")
    print("[*] Save any file in your IDE for real-time synchronization (Press Ctrl+C to abort).\n")

    # Initial filesystem snapshot
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in IGNORED_NAMES]
        rel_root = Path(root).relative_to(src)
        for f in files:
            if f in IGNORED_NAMES:
                continue
            p = rel_root / f
            norm_rel = str(p).replace("\\", "/")
            snapshot[norm_rel] = (src / p).stat().st_mtime

    while True:
        try:
            current_files = set()
            matrix_dirty = False

            for root, dirs, files in os.walk(src):
                dirs[:] = [d for d in dirs if d not in IGNORED_NAMES]
                rel_root = Path(root).relative_to(src)

                for f in files:
                    if f in IGNORED_NAMES:
                        continue

                    rel_path = str(rel_root / f).replace("\\", "/")
                    full_path = src / rel_path
                    current_files.add(rel_path)

                    mtime = full_path.stat().st_mtime
                    if rel_path not in snapshot or mtime > snapshot[rel_path]:
                        anon_rel = obfuscate_single_file(
                            full_path, rel_path, out, key, aes, num_buckets
                        )
                        mapping[anon_rel] = rel_path
                        rev_mapping[rel_path] = anon_rel
                        snapshot[rel_path] = mtime
                        matrix_dirty = True
                        print(f"[+] Synced/Encrypted: {rel_path} -> {anon_rel}")

            # Handle deletions
            deleted_files = set(snapshot.keys()) - current_files
            for del_rel in deleted_files:
                if del_rel in rev_mapping:
                    anon_rel = rev_mapping[del_rel]
                    del mapping[anon_rel]
                    del rev_mapping[del_rel]
                    anon_file = out / Path(anon_rel)
                    if anon_file.exists():
                        anon_file.unlink()
                    matrix_dirty = True
                    print(f"[-] Deleted: {del_rel} (removed {anon_rel})")
                del snapshot[del_rel]

            if matrix_dirty:
                save_matrix(matrix_file, aes, mapping)

            time.sleep(interval)
        except KeyboardInterrupt:
            print("\n[*] Watcher terminated.")
            break