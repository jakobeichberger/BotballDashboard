"""3D-print rules of the Botball Game Review (2026: v1.4, "3D Print Rules").

1. Only PLA or PETG, in a grayscale color.
2. At most 6 printed parts between both robots at the table (every movable
   part counts; jigs that are not on a robot do not).
3. No single part may exceed the print volume of an Ender 3 V3 SE,
   220 mm × 220 mm × 250 mm.
4. The STL of every part on a robot is submitted during documentation
   Period 3 (regional tournaments).

The checks are advisory: a job that breaks a rule is still accepted and
carries the warning codes of ``job_warnings``; the head judge decides at the
table. The bounding box is read from the uploaded STL; other formats (3MF,
G-code, OBJ) are not measured.
"""

from __future__ import annotations

import asyncio
import re
import struct
from itertools import chain
from pathlib import Path

from core.concurrency import ProcessSemaphore

ALLOWED_MATERIALS = ("PLA", "PETG")
#: Ender 3 V3 SE build volume in mm (x, y, z).
BUILD_VOLUME_MM = (220.0, 220.0, 250.0)
MAX_ROBOT_PARTS = 6
#: A job prints parts for a robot, spare copies for the judges (rule 3a), or
#: positioning jigs (rule 5a) — only robot parts count towards the limit.
PURPOSES = ("robot", "spare", "jig")

_GREY_NAMES = frozenset(
    {
        "black",
        "white",
        "grey",
        "gray",
        "silver",
        "light grey",
        "light gray",
        "dark grey",
        "dark gray",
        "schwarz",
        "weiß",
        "weiss",
        "grau",
        "hellgrau",
        "dunkelgrau",
        "silber",
    }
)
_HEX = re.compile(r"^#?([0-9a-f]{6})$", re.IGNORECASE)
_VERTEX = re.compile(rb"vertex\s+(\S+)\s+(\S+)\s+(\S+)")


def is_greyscale(color: str | None) -> bool | None:
    """True/False for a recognised color, None when it cannot be told."""
    if not color or not color.strip():
        return None
    value = color.strip().lower()
    match = _HEX.match(value)
    if match:
        digits = match.group(1)
        red, green, blue = (int(digits[i : i + 2], 16) for i in (0, 2, 4))
        return max(red, green, blue) - min(red, green, blue) <= 8
    if value in _GREY_NAMES:
        return True
    return False


def fits_build_volume(dimensions: tuple[float, float, float]) -> bool:
    """A part may be turned: compare the sorted sizes with the sorted volume."""
    return all(
        size <= limit + 0.01
        for size, limit in zip(sorted(dimensions), sorted(BUILD_VOLUME_MM), strict=True)
    )


#: Triangles per block of a binary STL (50 bytes each: ~3 MB at a time).
_BINARY_BLOCK_TRIANGLES = 65_536
#: Bytes per read of an ASCII STL.
_ASCII_CHUNK_BYTES = 256 * 1024
#: A "vertex x y z" line is short; a longer tail without one is garbage.
_ASCII_MAX_CARRY = 4096
#: Measurements running at once per API process (each holds a worker thread
#: and up to a block of the file in memory).
STL_CONCURRENT_MEASUREMENTS = 2
_MEASURE_SLOTS = ProcessSemaphore(STL_CONCURRENT_MEASUREMENTS)


async def measure_stl(path: str | Path) -> tuple[float, float, float] | None:
    """``stl_bounding_box`` in a worker thread, at most a few at a time."""
    async with _MEASURE_SLOTS:
        return await asyncio.to_thread(stl_bounding_box, path)


def stl_bounding_box(path: str | Path) -> tuple[float, float, float] | None:
    """Size (x, y, z) of an STL mesh in its units (mm), or None if unreadable.

    Streams the file: memory stays at a few MB whatever the file size (the
    upload limit is 100 MB, the API container has 1.5 GB).
    """
    path = Path(path)
    size = path.stat().st_size
    if size >= 84:
        with path.open("rb") as handle:
            header = handle.read(84)
        (triangles,) = struct.unpack_from("<I", header, 80)
        if triangles and size == 84 + 50 * triangles:
            return _binary_box(path, triangles)
    return _ascii_box(path)


def _binary_box(path: Path, triangles: int) -> tuple[float, float, float] | None:
    import numpy as np

    record = np.dtype([("normal", "<f4", 3), ("vertices", "<f4", (3, 3)), ("attribute", "<u2")])
    low = np.full(3, np.inf)
    high = np.full(3, -np.inf)
    # Read block by block (a memory map would grow the process RSS by the
    # whole file as its pages are touched).
    with path.open("rb") as handle:
        handle.seek(84)
        remaining = triangles
        while remaining:
            block = np.fromfile(handle, dtype=record, count=min(remaining, _BINARY_BLOCK_TRIANGLES))
            if not len(block):
                return None
            remaining -= len(block)
            vertices = block["vertices"]
            # min/max over triangles and corners of the strided view: no
            # reshaped copy. NaN propagates, so the result's finiteness
            # stands for every vertex's.
            low = np.minimum(low, vertices.min(axis=(0, 1)))
            high = np.maximum(high, vertices.max(axis=(0, 1)))
    if not (np.isfinite(low).all() and np.isfinite(high).all()):
        return None
    size = high - low
    return (float(size[0]), float(size[1]), float(size[2]))


def _ascii_box(path: Path) -> tuple[float, float, float] | None:
    import numpy as np

    low = np.full(3, np.inf)
    high = np.full(3, -np.inf)
    found = False
    carry = b""
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(_ASCII_CHUNK_BYTES)
            data = carry + chunk
            if chunk:
                # Keep a vertex that may continue in the next chunk for then.
                cut = data.rfind(b"vertex")
                if cut < 0:
                    cut = max(0, len(data) - len(b"vertex"))
                elif len(data) - cut > _ASCII_MAX_CARRY:
                    cut = len(data) - len(b"vertex")
                data, carry = data[:cut], data[cut:]
            matches = _VERTEX.findall(data)
            if matches:
                try:
                    values = list(map(float, chain.from_iterable(matches)))
                except ValueError:
                    return None
                points = np.array(values).reshape(-1, 3)
                found = True
                low = np.minimum(low, points.min(axis=0))
                high = np.maximum(high, points.max(axis=0))
            if not chunk:
                break
    if not found:
        return None
    size = high - low
    return (float(size[0]), float(size[1]), float(size[2]))


def job_warnings(
    material: str | None,
    color: str | None,
    dimensions: tuple[float, float, float] | None,
) -> list[str]:
    """Warning codes of one job: material, color, build volume."""
    warnings = []
    if (material or "").strip().upper() not in ALLOWED_MATERIALS:
        warnings.append("material_not_allowed")
    if is_greyscale(color) is False:
        warnings.append("color_not_greyscale")
    if dimensions is not None and not fits_build_volume(dimensions):
        warnings.append("exceeds_build_volume")
    return warnings
