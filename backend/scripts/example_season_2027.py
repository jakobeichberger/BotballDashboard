"""Print or create the documented example season ECER 2027.

    python scripts/example_season_2027.py            # print the payload (JSON)
    python scripts/example_season_2027.py --apply    # create it as a draft season

The data is modules.seasons.examples.ECER_2027 (ECER 2027, 5–9 April 2027,
Linzer Technikum, Linz; Botball registration closes 15 December 2026). The
season is created as a draft with the ECER 2026 formula presets as a starting
point; nothing is created unless --apply is given, and a season "ECER 2027"
that already exists is left alone.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def apply() -> None:
    import core.modules  # noqa: F401  (registers every model with the metadata)
    from core.database import AsyncSessionLocal
    from modules.seasons.examples import create_example_season_2027

    async with AsyncSessionLocal() as db:
        season = await create_example_season_2027(db)
        await db.commit()
        print(f"Created draft season {season.name} ({season.id})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="create the draft season")
    args = parser.parse_args()
    if args.apply:
        asyncio.run(apply())
        return
    from modules.seasons.examples import example_2027

    print(json.dumps(example_2027(), indent=2, default=str, ensure_ascii=False))


if __name__ == "__main__":
    main()
