import argparse
import sys
from brokenmirror.core import obfuscate_repository, restore_repository


def main():
    parser = argparse.ArgumentParser(
        prog="brokenmirror",
        description="BrokenMirror: Stealth topological repository obfuscation & reconstruction.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcomanda: obfuscate
    obf_p = subparsers.add_parser("obfuscate", help="Shatter and encrypt a repository.")
    obf_p.add_argument("-s", "--src", required=True, help="Source repository path.")
    obf_p.add_argument("-o", "--out", required=True, help="Target path for shattered files.")
    obf_p.add_argument("-m", "--matrix", default="matrix.enc", help="Encrypted cipher matrix destination path.")
    obf_p.add_argument("-b", "--buckets", type=int, default=8, help="Number of shard folders (default: 8).")

    # Subcomanda: restore
    res_p = subparsers.add_parser("restore", help="Reconstruct a repository from shattered files.")
    res_p.add_argument("-s", "--src", required=True, help="Shattered repository path.")
    res_p.add_argument("-o", "--out", required=True, help="Destination path for reconstructed code.")
    res_p.add_argument("-m", "--matrix", required=True, help="Path to matrix.enc.")
    res_p.add_argument("-k", "--key", required=True, help="Base64 AES decryption key.")

    args = parser.parse_args()

    try:
        if args.command == "obfuscate":
            key_b64, count = obfuscate_repository(args.src, args.out, args.matrix, args.buckets)
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
    except Exception as e:
        print(f"\n[-] Critical failure: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()