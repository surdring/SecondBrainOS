from __future__ import annotations

import sys
from pathlib import Path


def _fix_trailing_whitespace(text: str) -> tuple[str, bool]:
    changed = False
    out_lines: list[str] = []
    # Preserve final newline behavior by splitting with keepends
    for line in text.splitlines(keepends=True):
        if line.endswith("\r\n"):
            body, eol = line[:-2], "\r\n"
        elif line.endswith("\n"):
            body, eol = line[:-1], "\n"
        elif line.endswith("\r"):
            body, eol = line[:-1], "\r"
        else:
            body, eol = line, ""

        new_body = body.rstrip(" \t")
        if new_body != body:
            changed = True
        out_lines.append(new_body + eol)

    return "".join(out_lines), changed


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

        fixed, changed = _fix_trailing_whitespace(original)
        if changed:
            p.write_text(fixed, encoding="utf-8")
            modified.append(name)

    # pre-commit convention: return non-zero if files modified
    if modified:
        sys.stderr.write("Trailing whitespace fixed in files:\n")
        for f in modified:
            sys.stderr.write(f"- {f}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
