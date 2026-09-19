import argparse
import base64
import sys
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from brokenmirror.core import (
    init_dual_envelope_matrix,
    decrypt_payload,
    unlock_dek_from_matrix,
)


def main():
    parser = argparse.ArgumentParser(
        prog="brokenmirror",
        description="BrokenMirror: Zero-Disk Encrypted Dev & Multi-Key Envelope Obfuscation.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: init
    init_p = subparsers.add_parser("init", help="Initialize repository matrix with dual key slots (User + Backup).")
    init_p.add_argument("-m", "--matrix", required=True, help="Target matrix file path.")

    # Subcommand: mount-dev (Read-Write for VS Code / Local Dev)
    mdev_p = subparsers.add_parser("mount-dev", help="Mount encrypted repository as read-write RAM directory for IDE.")
    mdev_p.add_argument("-s", "--src", required=True, help="Shattered/encrypted repository path.")
    mdev_p.add_argument("-t", "--target", required=True, help="Target virtual directory for IDE.")
    mdev_p.add_argument("-m", "--matrix", required=True, help="Matrix path.")
    mdev_p.add_argument("-k", "--key", required=True, help="User Key OR Backup Recovery Key.")
    mdev_p.add_argument("--background", action="store_true", help="Run in background.")

    # Subcommand: diff-decrypt (for Git textconv)
    diff_p = subparsers.add_parser("diff-decrypt", help="Decrypt single file to stdout for Git textconv diff.")
    diff_p.add_argument("-k", "--key", required=True, help="User Key OR Backup Recovery Key.")
    diff_p.add_argument("-m", "--matrix", required=True, help="Path to matrix file.")
    diff_p.add_argument("file", nargs="?", default=None, help="Encrypted .bin file path.")

    args = parser.parse_args()

    try:
        if args.command == "init":
            user_k = base64.b64encode(AESGCM.generate_key(bit_length=256)).decode("ascii")
            backup_k = base64.b64encode(AESGCM.generate_key(bit_length=256)).decode("ascii")
            init_dual_envelope_matrix(Path(args.matrix), user_k, backup_k)

            print("\n[+] DUAL-KEY ENVELOPE INITIALIZED")
            print(f"    Matrix Path  : {args.matrix}")
            print(f"    User Key     : {user_k}")
            print(f"    Backup Key   : {backup_k}")
            print("    [!] Store Backup Key in a secure offline location!\n")

        elif args.command == "mount-dev":
            from brokenmirror.vfs import mount_rw_vfs
            print(f"[*] Mounting Read-Write VFS on {args.target}...")
            print("[*] Open this path in VS Code. All disk changes will be strictly encrypted.")
            mount_rw_vfs(args.src, args.target, args.matrix, args.key, foreground=not args.background)

        elif args.command == "diff-decrypt":
            if not args.file:
                sys.exit(0)
            target_path = Path(args.file).resolve()
            if not target_path.exists() or target_path.stat().st_size == 0:
                sys.exit(0)

            data = target_path.read_bytes()
            if len(data) < 28:
                sys.stdout.buffer.write(data)
                sys.exit(0)

            dek, _ = unlock_dek_from_matrix(Path(args.matrix), args.key)
            aes = AESGCM(dek)
            decrypted = decrypt_payload(aes, data)
            sys.stdout.buffer.write(decrypted)
            sys.exit(0)

    except Exception as e:
        if args.command == "diff-decrypt":
            sys.exit(0)
        print(f"\n[-] Critical failure: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()