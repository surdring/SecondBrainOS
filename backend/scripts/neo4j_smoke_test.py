from __future__ import annotations

import os
from pathlib import Path
from neo4j import GraphDatabase


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    force_override = {
        "NEO4J_URI",
        "NEO4J_USER",
        "NEO4J_USERNAME",
        "NEO4J_PASSWORD",
        "NEO4J_DATABASE",
    }
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            continue
        k, v = s.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if not k:
            continue
        if k in force_override or k not in os.environ:
            os.environ[k] = v


def main() -> None:
    _load_env_file(Path(__file__).resolve().parents[1] / ".env")
    uri = os.environ.get("NEO4J_URI")
    user = os.environ.get("NEO4J_USER") or os.environ.get("NEO4J_USERNAME")
    password = os.environ.get("NEO4J_PASSWORD")
    database = os.environ.get("NEO4J_DATABASE")

    missing = [
        k
        for k, v in {"NEO4J_URI": uri, "NEO4J_USER/NEO4J_USERNAME": user, "NEO4J_PASSWORD": password}.items()
        if not v
    ]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        try:
            with driver.session(database=database) as session:
                result = session.run("RETURN 1 AS one")
                row = result.single()
                if not row or row.get("one") != 1:
                    raise RuntimeError("Neo4j basic query failed")
        except Exception as e:
            raise RuntimeError(
                "Neo4j connection failed. Verify NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD in backend/.env"
            ) from e
    finally:
        driver.close()


if __name__ == "__main__":
    main()
