# BrokenMirror

BrokenMirror is a stealth topological repository obfuscation, zero-disk virtual filesystem (VFS), and dual-key envelope encryption tool designed for secure local development, transparent Git workflows, and hardened container execution.

Unlike traditional encryption tools that expose folder trees and file names, BrokenMirror breaks down repository topologies into deterministic buckets containing anonymized binary blobs (d_xxxx/f_xxxx.bin). With in-memory FUSE mounts, developers work in clear text inside their IDEs without leaving a single clear-text byte on disk, while remote Git hosts (GitHub, GitLab) store only opaque, structure-less ciphertext.

<br >

## Key Features

- Zero Cleartext on Disk: Editors access an in-memory virtual filesystem (FUSE). Disk writes are encrypted deterministically on flush/save.
- Dual-Key Envelope Encryption: Every repository is bound to a Master Data Encryption Key (DEK), wrapped inside two independent slots:
  - User Key: Primary credential for daily development and CI/CD pipelines.
  - Backup / Recovery Key: Secondary recovery key stored in an offline vault if the primary key is compromised or lost.
- Deterministic HMAC Topological Sharding: File paths are routed into uniform buckets via keyed HMAC-SHA256 digests. Identical paths map to identical target blocks, keeping Git history consistent and diffs minimal.
- Native Git Integration: Supports Git's textconv filter. Run git diff, git log -p, and inspect changes cleanly without decrypting files on disk.
- Containerized In-Memory Runtime: Ships with read-only FUSE runtime support for Docker, enabling workloads (Node.js, Go, Python, static assets) to boot directly from RAM.

<br />

## Prerequisites

- Python: >= 3.10
- System FUSE Library:
  - Ubuntu / Debian / Mint: sudo apt update && sudo apt install -y libfuse2
  - Fedora / RHEL: sudo dnf install -y fuse-libs
  - Arch Linux: sudo pacman -S fuse2
  - Alpine Linux (Docker): apk add --no-cache fuse

Ensure user_allow_other is enabled in `/etc/fuse.conf` if running as a non-root user:

```bash
echo "user_allow_other" | sudo tee -a /etc/fuse.conf
sudo chmod 644 /etc/fuse.conf
```

<br />

## Installation

Install in editable mode for local development:

```bash
git clone https://github.com/your-org/brokenmirror.git
cd brokenmirror
pip install -e .
```

<br />

## Architecture Overview

<img width="391" height="207" alt="image" src="https://github.com/user-attachments/assets/1e2ed101-804b-4cea-bc52-69a1a23feb72" />

<br />

## Quickstart

### 1. Initialize a Dual-Key Envelope

Generate the project matrix and create both the primary user key and the backup recovery key:

```bash
brokenmirror init -m /path/to/keys/project.key
```

**Output**

```bash
[+] DUAL-KEY ENVELOPE INITIALIZED
    Matrix Path  : /path/to/keys/project.key
    User Key     : <BASE64_USER_KEY>
    Backup Key   : <BASE64_BACKUP_KEY>
    [!] Store Backup Key in a secure offline location!
```
 
<br />

### 2. Import an Existing Repository

Convert a standard cleartext repository into a shattered BrokenMirror structure:

```bash
# 1. Initialize encrypted repository directory
mkdir -p /path/to/repo-encrypted
cd /path/to/repo-encrypted
git init

# 2. Configure transparent git diff
cat << 'EOF' > .gitattributes
*.bin diff=bm_diff
.gitkeep -diff
EOF

git config diff.bm_diff.textconv "brokenmirror diff-decrypt -m '/path/to/keys/project.key' -k '<BASE64_USER_KEY>'"

# 3. Seed cleartext files into encrypted repository
brokenmirror seed \
    -s /path/to/clear-project \
    -o /path/to/repo-encrypted \
    -m /path/to/keys/project.key \
    -k "<BASE64_USER_KEY>"

# 4. Commit encrypted artifacts
git add .
git commit -m "chore: initial shattered encrypted import"

# 5. Safely remove original cleartext directory
rm -rf /path/to/clear-project
```

<br />

### 3. Mount for Zero-Disk Editing (mount-dev)

Mount the encrypted directory as a read-write virtual filesystem in RAM:

```bash
mkdir -p ~/work/live-project

brokenmirror mount-dev \
    -s /path/to/repo-encrypted \
    -m /path/to/keys/project.key \
    -t ~/work/live-project \
    -k "<BASE64_USER_KEY>"
```

Open ~/work/live-project in any IDE (e.g., code ~/work/live-project).

- Files are decrypted on-the-fly into RAM during read() operations.
- File changes are encrypted with the DEK and flushed to /path/to/repo-encrypted/ upon save.

To unmount:

```bash
fusermount -u ~/work/live-project
```

### 4. Git Diff Inspection

Because `.gitattributes` links `*.bin` to `diff=bm_diff`, running standard Git commands inside /path/to/repo-encrypted renders clear text diffs seamlessly:

```bash
cd /path/to/repo-encrypted
git diff
```

<br />

## Production Docker Deployment

Run the encrypted repository inside a secure, ephemeral container.

> Dockerfile

```Dockerfile
FROM alpine:3.19

RUN apk add --no-cache python3 py3-pip fuse nodejs
RUN echo "user_allow_other" >> /etc/fuse.conf

WORKDIR /opt/brokenmirror
COPY . .
RUN pip install --break-system-packages .

WORKDIR /app
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["node", "index.js"]
```

<br />

> entrypoint.sh

```bash
#!/bin/sh
set -e

if [ -z "$BM_KEY" ]; then
    echo "[-] Error: BM_KEY environment variable is required."
    exit 1
fi

mkdir -p /app/live

# Mount read-only virtual filesystem
python3 -m brokenmirror.cli mount \
    -s /app/encrypted \
    -t /app/live \
    -m /app/matrix.key \
    -k "$BM_KEY" \
    --background

sleep 1
cd /app/live
exec "$@"
```

<br />

> Execution

```bash
docker run --rm \
    --device /dev/fuse \
    --cap-add SYS_ADMIN \
    -v "/path/to/repo-encrypted:/app/encrypted:ro" \
    -v "/path/to/keys/project.key:/app/matrix.key:ro" \
    -e BM_KEY="<BASE64_USER_KEY>" \
    my-secure-app
``` 

<br />

## Recovery Workflow

If a developer loses their primary User Key, no re-encryption of repository artifacts is required; access is restored via the secondary envelope slot

- The administrator retrieves the offline Backup Key.
- The administrator mounts the repository or unlocks the DEK:

```bash
brokenmirror mount-dev \
    -s /path/to/repo-encrypted \
    -m /path/to/keys/project.key \
    -t /tmp/recovery-mount \
    -k "<BASE64_BACKUP_KEY>"
```

<br />

## Support 

Github issues tracker or my personal X account:

[Sm0ke](https://x.com/Sm0keDev)

<br />

---
BrokenMirror - stealth source code obfuscation utility
