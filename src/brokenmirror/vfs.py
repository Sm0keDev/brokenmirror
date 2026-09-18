import base64
import errno
import os
import stat
import time
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fuse import FUSE, FuseOSError, Operations
from brokenmirror.core import decrypt_payload, load_or_create_matrix


class BrokenMirrorFS(Operations):
    """Read-only in-memory virtual filesystem backed by encrypted brokenmirror artifacts."""

    def __init__(self, obf_dir: str, matrix_path: str, key_b64: str):
        self.obf_dir = Path(obf_dir).resolve()
        self.key = base64.b64decode(key_b64)
        self.aes = AESGCM(self.key)
        self.matrix_path = Path(matrix_path).resolve()

        # Load and invert mapping: { "path/in/vfs.js": "d_0001/f_xxxx.bin" }
        raw_matrix = load_or_create_matrix(self.matrix_path, self.aes)
        self.file_map = {v.strip("/"): k for k, v in raw_matrix.items()}

        # Build directory index
        self.dir_children = {"": set()}
        for clear_path in self.file_map.keys():
            parts = clear_path.split("/")
            for i in range(len(parts) - 1):
                parent = "/".join(parts[:i])
                child = parts[i]
                self.dir_children.setdefault(parent, set()).add(child)
            parent = "/".join(parts[:-1])
            self.dir_children.setdefault(parent, set()).add(parts[-1])

        # Cache for decrypted files in RAM to avoid decrypting on every single read chunk
        self._cache = {}

    def _get_file_bytes(self, clean_path: str) -> bytes:
        if clean_path in self._cache:
            return self._cache[clean_path]

        anon_rel = self.file_map.get(clean_path)
        if not anon_rel:
            raise FuseOSError(errno.ENOENT)

        anon_full = self.obf_dir / anon_rel
        if not anon_full.exists():
            raise FuseOSError(errno.ENOENT)

        raw_enc = anon_full.read_bytes()
        decrypted = decrypt_payload(self.aes, raw_enc)
        self._cache[clean_path] = decrypted
        return decrypted

    def getattr(self, path: str, fh=None):
        clean_path = path.strip("/")
        now = time.time()

        # Root directory
        if clean_path == "":
            return {
                "st_mode": stat.S_IFDIR | 0o555,
                "st_nlink": 2,
                "st_size": 4096,
                "st_ctime": now,
                "st_mtime": now,
                "st_atime": now,
            }

        # Subdirectory
        if clean_path in self.dir_children:
            return {
                "st_mode": stat.S_IFDIR | 0o555,
                "st_nlink": 2,
                "st_size": 4096,
                "st_ctime": now,
                "st_mtime": now,
                "st_atime": now,
            }

        # Regular File
        if clean_path in self.file_map:
            content = self._get_file_bytes(clean_path)
            return {
                "st_mode": stat.S_IFREG | 0o444,
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

    def read(self, path: str, size: int, offset: int, fh=None) -> bytes:
        clean_path = path.strip("/")
        content = self._get_file_bytes(clean_path)
        return content[offset : offset + size]

    def open(self, path: str, flags: int):
        clean_path = path.strip("/")
        if clean_path not in self.file_map:
            raise FuseOSError(errno.ENOENT)
        # Read-only check
        accmode = flags & (os.O_RDONLY | os.O_WRONLY | os.O_RDWR)
        if accmode != os.O_RDONLY:
            raise FuseOSError(errno.EACCES)
        return 0


def mount_vfs(obf_dir: str, mount_point: str, matrix_path: str, key_b64: str, foreground: bool = True):
    mount = Path(mount_point).resolve()
    mount.mkdir(parents=True, exist_ok=True)
    operations = BrokenMirrorFS(obf_dir, matrix_path, key_b64)
    FUSE(operations, str(mount), foreground=foreground, ro=True, allow_other=True)