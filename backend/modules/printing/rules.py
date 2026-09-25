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

import re
import struct
from pathlib import Path

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


def stl_bounding_box(path: str | Path) -> tuple[float, float, float] | None:
    """Size (x, y, z) of an STL mesh in its units (mm), or None if unreadable."""
    data = Path(path).read_bytes()
    if len(data) >= 84:
        (triangles,) = struct.unpack_from("<I", data, 80)
        if triangles and len(data) == 84 + 50 * triangles:
            return _binary_box(data, triangles)
    return _ascii_box(data)


def _binary_box(data: bytes, triangles: int) -> tuple[float, float, float] | None:
    import numpy as np

    record = np.dtype([("normal", "<f4", 3), ("vertices", "<f4", (3, 3)), ("attribute", "<u2")])
    mesh = np.frombuffer(data, dtype=record, count=triangles, offset=84)
    points = mesh["vertices"].reshape(-1, 3)
    if not np.isfinite(points).all():
        return None
    size = points.max(axis=0) - points.min(axis=0)
    return (float(size[0]), float(size[1]), float(size[2]))


def _ascii_box(data: bytes) -> tuple[float, float, float] | None:
    low = [float("inf")] * 3
    high = [float("-inf")] * 3
    found = False
    for match in _VERTEX.finditer(data):
        try:
            point = [float(value) for value in match.groups()]
        except ValueError:
            return None
        found = True
        for axis in range(3):
            low[axis] = min(low[axis], point[axis])
            high[axis] = max(high[axis], point[axis])
    if not found:
        return None
    return (high[0] - low[0], high[1] - low[1], high[2] - low[2])


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
