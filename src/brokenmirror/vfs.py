import errno
import os
import stat
import time
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fuse import FUSE, FuseOSError, Operations
from brokenmirror.core import (
    get_deterministic_paths,
    encrypt_payload,
    decrypt_payload,
    unlock_dek_from_matrix,
    save_matrix_payload,
)


class BrokenMirrorDevFS(Operations):
    """Read-Write in-memory virtual filesystem backed exclusively by encrypted disk artifacts."""

    def __init__(self, obf_dir: str, matrix_path: str, key_b64: str, num_buckets: int = 8):
        self.obf_dir = Path(obf_dir).resolve()
        self.matrix_path = Path(matrix_path).resolve()
        self.num_buckets = num_buckets

        self.dek, self.orig_map = unlock_dek_from_matrix(self.matrix_path, key_b64)
        self.aes = AESGCM(self.dek)

        # Mapping: { "relative/clean/path.js": "d_0001/f_xxxx.bin" }
        self.file_map = {v.strip("/"): k for k, v in self.orig_map.items()}

        self._cache = {}
        self._dirty_files = set()
        self._rebuild_dir_index()

    def _rebuild_dir_index(self):
        self.dir_children = {"": set()}
        for clear_path in self.file_map.keys():
            parts = clear_path.split("/")
            for i in range(len(parts) - 1):
                parent = "/".join(parts[:i])
                child = parts[i]
                self.dir_children.setdefault(parent, set()).add(child)
            parent = "/".join(parts[:-1])
            self.dir_children.setdefault(parent, set()).add(parts[-1])

    def _get_file_bytes(self, clean_path: str) -> bytearray:
        if clean_path in self._cache:
            return self._cache[clean_path]

        anon_rel = self.file_map.get(clean_path)
        if not anon_rel:
            raise FuseOSError(errno.ENOENT)

        anon_full = self.obf_dir / anon_rel
        if not anon_full.exists():
            return bytearray()

        raw_enc = anon_full.read_bytes()
        decrypted = decrypt_payload(self.aes, raw_enc)
        b_data = bytearray(decrypted)
        self._cache[clean_path] = b_data
        return b_data

    def getattr(self, path: str, fh=None):
        clean_path = path.strip("/")
        now = time.time()

        if clean_path == "" or clean_path in self.dir_children:
            return {
                "st_mode": stat.S_IFDIR | 0o755,
                "st_nlink": 2,
                "st_size": 4096,
                "st_ctime": now,
                "st_mtime": now,
                "st_atime": now,
            }

        if clean_path in self.file_map:
            content = self._get_file_bytes(clean_path)
            return {
                "st_mode": stat.S_IFREG | 0o644,
                "st_nlink": 1,
                "st_size": len(content),
                "st_ctime": now,
                "st_mtime": now,
                "st_atime": now,
            }

        raise FuseOSError(errno.ENOENT)

    def readdir(self, path: str, fh=None):
        clean_path = path.strip("/")
        if clean_path not in self.dir_children:
            raise FuseOSError(errno.ENOENT)

        entries = [".", ".."] + sorted(list(self.dir_children[clean_path]))
        for entry in entries:
            yield entry

    def mkdir(self, path: str, mode):
        clean_path = path.strip("/")
        if clean_path in self.dir_children or clean_path in self.file_map:
            raise FuseOSError(errno.EEXIST)

        parts = clean_path.split("/")
        parent = "/".join(parts[:-1])
        self.dir_children.setdefault(parent, set()).add(parts[-1])
        self.dir_children.setdefault(clean_path, set())
        return 0

    def rmdir(self, path: str):
        clean_path = path.strip("/")
        if clean_path not in self.dir_children:
            raise FuseOSError(errno.ENOENT)
        if self.dir_children[clean_path]:
            raise FuseOSError(errno.ENOTEMPTY)

        parts = clean_path.split("/")
        parent = "/".join(parts[:-1])
        if parent in self.dir_children:
            self.dir_children[parent].discard(parts[-1])
        del self.dir_children[clean_path]
        return 0

    def create(self, path: str, mode, fi=None):
        clean_path = path.strip("/")
        self._cache[clean_path] = bytearray()
        self._dirty_files.add(clean_path)

        bucket, anon_rel = get_deterministic_paths(clean_path, self.dek, self.num_buckets)
        self.file_map[clean_path] = anon_rel

        parts = clean_path.split("/")
        parent = "/".join(parts[:-1])
        self.dir_children.setdefault(parent, set()).add(parts[-1])
        return 0

    def open(self, path: str, flags):
        return 0

    def read(self, path: str, size: int, offset: int, fh=None) -> bytes:
        clean_path = path.strip("/")
        content = self._get_file_bytes(clean_path)
        return bytes(content[offset : offset + size])

    def write(self, path: str, data: bytes, offset: int, fh=None) -> int:
        clean_path = path.strip("/")
        content = self._get_file_bytes(clean_path)

        end_pos = offset + len(data)
        if end_pos > len(content):
            content.extend(b"\x00" * (end_pos - len(content)))

        content[offset:end_pos] = data
        self._cache[clean_path] = content
        self._dirty_files.add(clean_path)
        return len(data)

    def truncate(self, path: str, length: int, fh=None):
        clean_path = path.strip("/")
        content = self._get_file_bytes(clean_path)
        if length < len(content):
            self._cache[clean_path] = content[:length]
        else:
            content.extend(b"\x00" * (length - len(content)))
            self._cache[clean_path] = content
        self._dirty_files.add(clean_path)
        return 0

    def unlink(self, path: str):
        clean_path = path.strip("/")
        if clean_path not in self.file_map:
            raise FuseOSError(errno.ENOENT)

        anon_rel = self.file_map[clean_path]
        anon_full = self.obf_dir / anon_rel
        if anon_full.exists():
            anon_full.unlink()

        del self.file_map[clean_path]
        self._cache.pop(clean_path, None)
        self._dirty_files.discard(clean_path)

        parts = clean_path.split("/")
        parent = "/".join(parts[:-1])
        if parent in self.dir_children:
            self.dir_children[parent].discard(parts[-1])

        rev_map = {v: k for k, v in self.file_map.items()}
        save_matrix_payload(self.matrix_path, self.dek, rev_map)
        return 0

    def flush(self, path: str, fh=None):
        clean_path = path.strip("/")
        if clean_path in self._dirty_files:
            content = self._cache[clean_path]
            anon_rel = self.file_map[clean_path]
            anon_full = self.obf_dir / anon_rel

            anon_full.parent.mkdir(parents=True, exist_ok=True)
            enc_data = encrypt_payload(self.aes, bytes(content))
            anon_full.write_bytes(enc_data)

            self._dirty_files.discard(clean_path)

            rev_map = {v: k for k, v in self.file_map.items()}
            save_matrix_payload(self.matrix_path, self.dek, rev_map)
        return 0


def mount_rw_vfs(obf_dir: str, mount_point: str, matrix_path: str, key_b64: str, foreground: bool = True):
    mount = Path(mount_point).resolve()
    mount.mkdir(parents=True, exist_ok=True)
    operations = BrokenMirrorDevFS(obf_dir, matrix_path, key_b64)
    FUSE(operations, str(mount), foreground=foreground, ro=False, allow_other=True)