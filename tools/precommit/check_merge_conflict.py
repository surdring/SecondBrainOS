from __future__ import annotations

import sys
from pathlib import Path


CONFLICT_MARKERS = ("<<<<<<<", "=======", ">>>>>>>")


def _has_conflict_markers(text: str) -> bool:
    for line in text.splitlines():
        s = line.lstrip()
        if any(s.startswith(m) for m in CONFLICT_MARKERS):
            return True
    return False


def main(argv: list[str]) -> int:
    failed: list[str] = []
    for name in argv[1:]:
        p = Path(name)
        if not p.exists() or p.is_dir():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # binary / non-utf8: ignore
            continue
        if _has_conflict_markers(text):
            failed.append(name)

    if failed:
        sys.stderr.write("Merge conflict markers found in files:\n")
        for f in failed:
            sys.stderr.write(f"- {f}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
