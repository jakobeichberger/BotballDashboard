"""The STL bounding box is measured without loading the file into memory.

A 100 MB STL used to cost ~200 MB (binary: the file plus a reshaped copy)
or a per-vertex Python loop over the whole file (ASCII) in the API process;
a few concurrent uploads near the print deadline could OOM-kill the API.
"""

import asyncio
import tracemalloc

import numpy as np
import pytest

from modules.printing import rules

TRIANGLES = 600_000  # 30 MB binary STL


def _binary_stl(path, triangles: int) -> None:
    record = np.dtype([("normal", "<f4", 3), ("vertices", "<f4", (3, 3)), ("attribute", "<u2")])
    mesh = np.zeros(triangles, dtype=record)
    rng = np.random.default_rng(1)
    mesh["vertices"] = rng.uniform(0, 100, size=(triangles, 3, 3)).astype("<f4")
    # Known extremes somewhere in the middle of the file.
    mesh["vertices"][triangles // 2] = [[-10, -20, -30], [150, 0, 0], [0, 170, 190]]
    with open(path, "wb") as handle:
        handle.write(b"synthetic".ljust(80, b" "))
        handle.write(np.uint32(triangles).tobytes())
        mesh.tofile(handle)


def _ascii_stl(path, facets: int) -> None:
    with open(path, "wb") as handle:
        handle.write(b"solid big\n")
        facet = (
            b"facet normal 0 0 1\n outer loop\n  vertex %d 0 0\n  vertex 0 %d 0\n"
            b"  vertex 0 0 %d\n endloop\nendfacet\n"
        )
        for index in range(facets):
            handle.write(facet % (index % 50, index % 60, index % 70))
        handle.write(b"endsolid big\n")


def _peak_mib(func, *args):
    tracemalloc.start()
    try:
        result = func(*args)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return result, peak / 2**20


def test_binary_box_is_streamed(tmp_path):
    path = tmp_path / "big.stl"
    _binary_stl(path, TRIANGLES)
    assert path.stat().st_size == 84 + 50 * TRIANGLES
    box, peak = _peak_mib(rules.stl_bounding_box, path)
    assert box == pytest.approx((160, 190, 220), abs=1e-3)
    # Before: the 30 MB file plus a 21 MB copy of the vertices.
    assert peak < 16, f"peak {peak:.1f} MiB"


def test_binary_box_with_non_finite_vertices_is_unknown(tmp_path):
    path = tmp_path / "nan.stl"
    _binary_stl(path, 1000)
    data = bytearray(path.read_bytes())
    data[84 + 50 * 700 + 12 : 84 + 50 * 700 + 16] = np.float32("nan").tobytes()
    path.write_bytes(bytes(data))
    assert rules.stl_bounding_box(path) is None


def test_ascii_box_is_parsed_in_chunks(tmp_path):
    path = tmp_path / "big_ascii.stl"
    _ascii_stl(path, 100_000)  # ~9.5 MB
    box, peak = _peak_mib(rules.stl_bounding_box, path)
    assert box == pytest.approx((49, 59, 69))
    # Before: the whole file as one bytes object.
    assert peak < 5, f"peak {peak:.1f} MiB"


def test_ascii_vertex_split_across_chunks(tmp_path, monkeypatch):
    monkeypatch.setattr(rules, "_ASCII_CHUNK_BYTES", 7)
    path = tmp_path / "tiny.stl"
    path.write_bytes(
        b"solid x\nfacet normal 0 0 1\nouter loop\nvertex -5 0 0\nvertex 5 20 0\n"
        b"vertex 0 0 30.5\nendloop\nendfacet\nendsolid x\n"
    )
    assert rules.stl_bounding_box(path) == pytest.approx((10, 20, 30.5))


def test_ascii_with_a_broken_number_is_unknown(tmp_path):
    path = tmp_path / "bad.stl"
    path.write_bytes(b"solid x\nvertex 1 2 3\nvertex 1 two 3\nendsolid x\n")
    assert rules.stl_bounding_box(path) is None


@pytest.mark.asyncio
async def test_concurrent_measurements_are_limited(tmp_path, monkeypatch):
    path = tmp_path / "a.stl"
    _binary_stl(path, 10)
    active = peak = 0
    real = rules.stl_bounding_box

    def counting(p):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            import time

            time.sleep(0.05)
            return real(p)
        finally:
            active -= 1

    monkeypatch.setattr(rules, "stl_bounding_box", counting)
    boxes = await asyncio.gather(*(rules.measure_stl(path) for _ in range(8)))
    assert all(box is not None for box in boxes)
    assert peak <= rules.STL_CONCURRENT_MEASUREMENTS
