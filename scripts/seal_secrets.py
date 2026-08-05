#!/usr/bin/env python3
"""
Step 0.0: Secret 加密打包工具

用法:
  python scripts/seal_secrets.py seal   < .env.production > secrets.env.enc
  python scripts/seal_secrets.py verify < secrets.env.enc
  python scripts/seal_secrets.py export < secrets.env.enc  # 解密输出（仅本地调试）
"""
import sys
import json
import hashlib
import base64
import secrets
from datetime import datetime, timezone
from pathlib import Path
from cryptography.fernet import Fernet

CONFIG_VERSION = 1


def _derive_key(secret: str) -> bytes:
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())


def seal():
    """从 stdin 读取明文 .env，加密输出到 stdout"""
    plaintext = sys.stdin.read().encode("utf-8")
    key_bytes = secrets.token_bytes(32)
    key_b64 = base64.urlsafe_b64encode(key_bytes).decode("ascii")
    f = Fernet(_derive_key(key_b64))
    ciphertext = f.encrypt(plaintext).decode("ascii")
    sha = hashlib.sha256(plaintext).hexdigest()

    package = {
        "config_version": CONFIG_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat() + "Z",
        "sha256": sha,
        "ciphertext": ciphertext,
    }
    sys.stderr.write(f"\n=== DECRYPTION KEY (save separately!) ===\n{key_b64}\n==========================================\n\n")
    sys.stdout.write(json.dumps(package, indent=2, ensure_ascii=False))


def verify(path: str):
    """验证加密包完整性"""
    data = json.loads(Path(path).read_text())
    key_b64 = input("Decryption key: ").strip()
    f = Fernet(_derive_key(key_b64))
    plaintext = f.decrypt(data["ciphertext"].encode()).decode("utf-8")
    actual_sha = hashlib.sha256(plaintext.encode()).hexdigest()
    expected_sha = data["sha256"]

    print(f"config_version: {data['config_version']}")
    print(f"created_at:     {data['created_at']}")
    print(f"SHA256 match:   {actual_sha == expected_sha}")
    print(f"line count:     {len(plaintext.splitlines())}")
    if actual_sha != expected_sha:
        print("ERROR: SHA256 mismatch - file may be corrupted")
        sys.exit(1)
    print("OK: package integrity verified")


def export_cmd(path: str):
    """解密输出（仅本地调试用）"""
    data = json.loads(Path(path).read_text())
    key_b64 = input("Decryption key: ").strip()
    f = Fernet(_derive_key(key_b64))
    plaintext = f.decrypt(data["ciphertext"].encode()).decode("utf-8")
    sys.stdout.write(plaintext)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "seal":
        seal()
    elif cmd == "verify":
        verify(sys.argv[2])
    elif cmd == "export":
        export_cmd(sys.argv[2])
    else:
        print(f"unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
