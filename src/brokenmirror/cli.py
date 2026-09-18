import argparse
import base64
import sys
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from brokenmirror.core import (
    obfuscate_repository,
    restore_repository,
    watch_repository,
    decrypt_payload,
)


def main():
    parser = argparse.ArgumentParser(
        prog="brokenmirror",
        description="BrokenMirror: Stealth topological repository obfuscation, synchronization & VFS runtime.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: obfuscate
    obf_p = subparsers.add_parser("obfuscate", help="Shatter and encrypt a repository.")
    obf_p.add_argument("-s", "--src", required=True, help="Source repository path.")
    obf_p.add_argument(
        "-o", "--out", required=True, help="Target path for shattered files."
    )
    obf_p.add_argument("-m", "--matrix", default="matrix.enc", help="Matrix path.")
    obf_p.add_argument(
        "-k", "--key", default=None, help="Reuse existing base64 master key."
    )
    obf_p.add_argument(
        "-b", "--buckets", type=int, default=8, help="Number of shard folders."
    )

    # Subcommand: restore
    res_p = subparsers.add_parser("restore", help="Reconstruct a repository.")
    res_p.add_argument(
        "-s", "--src", required=True, help="Shattered repository path."
    )
    res_p.add_argument(
        "-o", "--out", required=True, help="Destination path for reconstructed code."
    )
    res_p.add_argument("-m", "--matrix", required=True, help="Path to matrix.")
    res_p.add_argument(
        "-k", "--key", required=True, help="Base64 AES decryption key."
    )

    # Subcommand: watch
    wat_p = subparsers.add_parser(
        "watch",
        help="Watch source repository and sync changes live to encrypted repo.",
    )
    wat_p.add_argument(
        "-s", "--src", required=True, help="Source directory (clear code)."
    )
    wat_p.add_argument(
        "-o", "--out", required=True, help="Target encrypted directory."
    )
    wat_p.add_argument("-m", "--matrix", required=True, help="Matrix path.")
    wat_p.add_argument(
        "-k", "--key", required=True, help="Base64 AES master key."
    )
    wat_p.add_argument(
        "-b", "--buckets", type=int, default=8, help="Number of shard folders."
    )

    # Subcommand: diff-decrypt (for Git textconv diff)
    diff_p = subparsers.add_parser(
        "diff-decrypt",
        help="Decrypt single file to stdout for Git textconv diff.",
    )
    diff_p.add_argument("-k", "--key", required=True, help="Base64 AES master key.")
    diff_p.add_argument("file", nargs="?", default=None, help="Encrypted .bin file path.")

    # Subcommand: mount (for FUSE runtime execution)
    mount_p = subparsers.add_parser(
        "mount",
        help="Mount encrypted repository as a read-only virtual RAM filesystem.",
    )
    mount_p.add_argument(
        "-s", "--src", required=True, help="Shattered/encrypted repository path."
    )
    mount_p.add_argument(
        "-t", "--target", required=True, help="Target mount directory (virtual)."
    )
    mount_p.add_argument("-m", "--matrix", required=True, help="Matrix path.")
    mount_p.add_argument(
        "-k", "--key", required=True, help="Base64 AES master key."
    )
    mount_p.add_argument(
        "--background", action="store_true", help="Run FUSE process in background."
    )

    args = parser.parse_args()

    try:
        if args.command == "obfuscate":
            key_b64, count = obfuscate_repository(
                args.src, args.out, args.matrix, args.key, args.buckets
            )
            print("\n[+] REPOSITORY SHATTERED")
            print(f"    Processed Files : {count}")
            print(f"    Output Path     : {args.out}")
            print(f"    Matrix Artifact : {args.matrix}")
            print(f"    Master Secret   : {key_b64}\n")

        elif args.command == "restore":
            count = restore_repository(args.src, args.out, args.matrix, args.key)
            print("\n[+] REPOSITORY RECONSTRUCTED")
            print(f"    Restored Files  : {count}")
            print(f"    Target Location : {args.out}\n")

        elif args.command == "watch":
            watch_repository(args.src, args.out, args.matrix, args.key, args.buckets)

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

            key = base64.b64decode(args.key)
            aes = AESGCM(key)
            decrypted = decrypt_payload(aes, data)
            sys.stdout.buffer.write(decrypted)
            sys.exit(0)

        elif args.command == "mount":
            from brokenmirror.vfs import mount_vfs

            print(f"[*] Mounting virtual filesystem on {args.target}...")
            mount_vfs(
                args.src,
                args.target,
                args.matrix,
                args.key,
                foreground=not args.background,
            )

    except Exception as e:
        if args.command == "diff-decrypt":
            sys.exit(0)
        print(f"\n[-] Critical failure: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()