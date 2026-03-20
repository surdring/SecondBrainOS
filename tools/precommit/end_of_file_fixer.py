from __future__ import annotations

import sys
from pathlib import Path


def _ensure_final_newline(text: str) -> tuple[str, bool]:
    if not text:
        return "\n", True
    if text.endswith("\n"):
        return text, False
    return text + "\n", True


def main(argv: list[str]) -> int:
    modified: list[str] = []
    for name in argv[1:]:
        p = Path(name)
        if not p.exists() or p.is_dir():
            continue
        try:
            original = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        fixed, changed = _ensure_final_newline(original)
        if changed:
            p.write_text(fixed, encoding="utf-8")
            modified.append(name)

    if modified:
        sys.stderr.write("End-of-file newline fixed in files:\n")
        for f in modified:
            sys.stderr.write(f"- {f}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
