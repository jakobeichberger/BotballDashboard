"""Migration round trip WITH data (CI job "PostgreSQL, Redis & Migrations").

The data-moving parts of the migrations (0034 aerial runs → list, 0032 outbox
status, 0033 clean-ups) only run when there are rows. This helper seeds such
rows on top of ``scripts/seed_e2e.py``, snapshots the database, and after
``alembic downgrade <rev>`` + ``alembic upgrade head`` compares it again:

    python scripts/seed_e2e.py
    python scripts/migration_roundtrip.py seed
    python scripts/migration_roundtrip.py snapshot /tmp/before.json
    alembic downgrade 0030 && alembic upgrade head
    python scripts/migration_roundtrip.py snapshot /tmp/after.json
    python scripts/migration_roundtrip.py compare /tmp/before.json /tmp/after.json

``compare`` fails when a table lost rows, unless the loss is one the
downgrades document (``DOCUMENTED_LOSS``), and checks the values that the
data migrations transform (first four aerial runs, outbox status).

``compare --update BEFORE AFTER`` checks an update (or a rollback) of a
running installation instead (CI job "Deployment – update"): no table may
lose rows; tables new in the target release may appear, the revision may
change, and the seeded aerial/outbox rows are not required.

Connection: POSTGRES_HOST/PORT/DB/USER/PASSWORD like the application.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from typing import Any

# Tables whose rows a downgrade below 0034 drops by design (see the
# docstrings of the migrations): created by 0034, so they are empty again
# after the re-upgrade.
DOCUMENTED_LOSS = {
    "season_categories",
    "jbc_results",
    "timeout_cards",
    "event_awards",
    "award_categories",
    "award_nominations",
    "award_results",
}
AERIAL_RUNS = [11.5, 12.0, 13.25, 14.0, 15.5, 16.0]
OUTBOX_MARKER = "migration-roundtrip"


async def _connect() -> Any:
    # Imported here: ``compare`` also runs on a CI host without the backend's
    # dependencies.
    import asyncpg

    return await asyncpg.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        database=os.environ.get("POSTGRES_DB", "botball"),
        user=os.environ.get("POSTGRES_USER", "botball"),
        password=os.environ.get("POSTGRES_PASSWORD", ""),
    )


async def seed() -> None:
    """Rows for the data migrations, on top of seed_e2e.py's event."""
    conn = await _connect()
    try:
        event = await conn.fetchrow(
            "SELECT e.id, e.season_id FROM events e WHERE e.slug = 'e2e-event'"
        )
        if event is None:
            raise SystemExit("run scripts/seed_e2e.py first (no event e2e-event)")
        teams = await conn.fetch(
            "SELECT team_id FROM event_registrations WHERE event_id = $1 ORDER BY team_id",
            event["id"],
        )
        # 0034: six aerial runs; the downgrade keeps four, the re-upgrade
        # brings those four back as the list.
        await conn.execute(
            "INSERT INTO aerial_results (id, season_id, event_id, team_id, runs) "
            "VALUES ($1, $2, $3, $4, $5::json) ON CONFLICT (event_id, team_id) "
            "DO UPDATE SET runs = EXCLUDED.runs",
            str(uuid.uuid4()),
            event["season_id"],
            event["id"],
            teams[0]["team_id"],
            json.dumps(AERIAL_RUNS),
        )
        # 0032: an outbox row claimed by a worker ("sending"); the downgrade
        # puts it back to "pending" before the old CHECK constraint returns.
        await conn.execute(
            "INSERT INTO notification_events (id, event_id, event_type, payload, status, "
            "attempts, dedupe_key) VALUES ($1, $2, 'match.reminder', '{}'::json, 'sending', 1, $3) "
            "ON CONFLICT (dedupe_key) DO NOTHING",
            str(uuid.uuid4()),
            event["id"],
            OUTBOX_MARKER,
        )
        # 0034: a season category (dropped by the downgrade, documented).
        await conn.execute(
            "INSERT INTO season_categories (id, season_id, key, label_de, label_en, kind) "
            "VALUES ($1, $2, 'roundtrip', 'Rundreise', 'Round trip', 'botball') "
            "ON CONFLICT DO NOTHING",
            str(uuid.uuid4()),
            event["season_id"],
        )
    finally:
        await conn.close()


async def snapshot(path: str) -> None:
    conn = await _connect()
    try:
        tables = [
            row["tablename"]
            for row in await conn.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1"
            )
        ]
        counts = {
            table: await conn.fetchval(f'SELECT count(*) FROM "{table}"')  # noqa: S608
            for table in tables
        }
        runs = await conn.fetchval(
            "SELECT runs::text FROM aerial_results a JOIN events e ON e.id = a.event_id "
            "WHERE e.slug = 'e2e-event' ORDER BY a.team_id LIMIT 1"
        )
        outbox = await conn.fetchval(
            "SELECT status FROM notification_events WHERE dedupe_key = $1", OUTBOX_MARKER
        )
        revision = await conn.fetchval("SELECT string_agg(version_num, ',') FROM alembic_version")
    finally:
        await conn.close()
    data = {
        "revision": revision,
        "counts": counts,
        "aerial_runs": json.loads(runs) if runs else None,
        "outbox_status": outbox,
    }
    with open(path, "w") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
    print(f"{path}: {len(counts)} tables, {sum(counts.values())} rows, revision {revision}")


def compare(before_path: str, after_path: str, update: bool = False) -> int:
    with open(before_path) as handle:
        before = json.load(handle)
    with open(after_path) as handle:
        after = json.load(handle)
    problems: list[str] = []
    if update:
        for table, count in sorted(before["counts"].items()):
            new = after["counts"].get(table)
            if new is None or new < count:
                problems.append(f"{table}: {count} rows before, {new} after")
        for problem in problems:
            print(f"FAIL {problem}")
        rows = sum(after["counts"].values())
        print(
            f"{before['revision']} → {after['revision']}: "
            + ("no rows lost" if not problems else f"{len(problems)} table(s) lost rows")
            + f" ({rows} rows in {len(after['counts'])} tables)"
        )
        return 1 if problems else 0
    if before["revision"] != after["revision"]:
        problems.append(f"revision {before['revision']} → {after['revision']}")
    for table, count in sorted(before["counts"].items()):
        new = after["counts"].get(table)
        if new is None:
            problems.append(f"table {table} missing after the round trip")
        elif new != count and not (table in DOCUMENTED_LOSS and new < count):
            problems.append(f"{table}: {count} rows before, {new} after")
    for table in sorted(set(after["counts"]) - set(before["counts"])):
        problems.append(f"unexpected new table {table}")
    # 0034 downgrade keeps the first four runs.
    if before["aerial_runs"] != AERIAL_RUNS:
        problems.append(f"seeded aerial runs missing before: {before['aerial_runs']}")
    if after["aerial_runs"] != AERIAL_RUNS[:4]:
        problems.append(f"aerial runs after the round trip: {after['aerial_runs']}")
    # 0032 downgrade resets claimed rows to pending.
    if after["outbox_status"] not in ("pending", "sending"):
        problems.append(f"outbox status after the round trip: {after['outbox_status']}")
    for problem in problems:
        print(f"FAIL {problem}")
    lost = {
        table: before["counts"][table] - after["counts"].get(table, 0)
        for table in DOCUMENTED_LOSS & set(before["counts"])
        if after["counts"].get(table, 0) < before["counts"][table]
    }
    print(f"documented downgrade losses: {lost or 'none'}")
    print("round trip OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] == "seed":
        asyncio.run(seed())
        return 0
    if len(argv) == 3 and argv[1] == "snapshot":
        asyncio.run(snapshot(argv[2]))
        return 0
    if len(argv) == 4 and argv[1] == "compare":
        return compare(argv[2], argv[3])
    if len(argv) == 5 and argv[1] == "compare" and argv[2] == "--update":
        return compare(argv[3], argv[4], update=True)
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
