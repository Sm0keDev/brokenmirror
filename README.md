# BrokenMirror

**BrokenMirror** is a stealth source code obfuscation utility. It destroys the static topological profile of a repository by flattening directory trees, stripping file extensions, scattering code chunks across randomized shard buckets, and encrypting contents with authenticated AES-256-GCM.

No static analysis tool (`file`, `linguist`, AST scanners) can detect the language, structure, or content without the encrypted cipher matrix and secret key.

<br />

## Pypi Installation (soon ...)

```bash
pip install brokenmirror
```

<br />

## Local Installation 

```bash
# create ENV and install deps
pip install requirements.txt
pip install -e .
brokenmirror --help # or the short alias:
bm --help           # for lazy devs  
```

<br />

## Quick Start

1. Shatter & Obfuscate a Repository

```bash
brokenmirror obfuscate -s ./my_project -o ./shattered_repo -m ./matrix.enc
```

> Flags:

- `-s`, --src: Source directory.
- `-o`, --out: Output directory for obfuscated files.
- `-m`, --matrix: Destination path for the encrypted mapping matrix.
- `-b`, --buckets: (Optional) Number of randomized bucket containers (default: 8).

<br />

2. Reconstruct & Restore

```bash
brokenmirror restore -s ./shattered_repo -o ./restored_project -m ./matrix.enc -k "BASE64_KEY"
```

> Flags:

- `-s`, --src: Obfuscated repo directory.
- `-o`, --out: Destination directory for restored source code.
- `-m`, --matrix: Path to matrix.enc.
- `-k`, --key: Secret Base64 key provided during obfuscation.

<br >

## Support 

Github issues tracker or my personal X account:

[Sm0ke](https://x.com/Sm0keDev)

<br />

---
BrokenMirror - stealth source code obfuscation utility
