from __future__ import annotations

import re
import sys
from pathlib import Path


PRIVATE_KEY_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"-----BEGIN PRIVATE KEY-----"),
]


def _looks_like_private_key(text: str) -> bool:
    return any(p.search(text) for p in PRIVATE_KEY_PATTERNS)


def main(argv: list[str]) -> int:
    failed: list[str] = []
    for name in argv[1:]:
        p = Path(name)
        if not p.exists() or p.is_dir():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if _looks_like_private_key(text):
            failed.append(name)

    if failed:
        sys.stderr.write("Potential private key material detected in files:\n")
        for f in failed:
            sys.stderr.write(f"- {f}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
