"""OCR input limits (security review 2026-09, #3).

A few-KB PNG could declare billions of pixels (decompression bomb) and
PDFs were rasterized at whatever size their page box asked for.
"""

import os
import struct
import zlib
from types import SimpleNamespace

import pytest
from PIL import Image

# ── 3. OCR image limits ───────────────────────────────────────────────────────


def _bomb_png(path, side: int):
    """A 1-bit PNG of side x side pixels that is only a few KB on disk."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)

    row = b"\x00" * (1 + (side + 7) // 8)
    compressor = zlib.compressobj(9)
    idat = b"".join(compressor.compress(row) for _ in range(side)) + compressor.flush()
    header = struct.pack(">IIBBBBB", side, side, 1, 0, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")
    )
    return path


def _scan(path, scan_id="scan-1"):
    return SimpleNamespace(file_url=str(path), id=scan_id)


def _template():
    return SimpleNamespace(
        page_width=None,
        page_height=None,
        anchors=[],
        field_regions=[],
        confirmed_fields=[],
        validation_rules=None,
    )


def test_decompression_bomb_is_rejected_before_decoding(tmp_path, monkeypatch):
    import cv2

    from modules.scoring.score_sheets import scan_service

    bomb = _bomb_png(tmp_path / "bomb.png", 8000)  # 64 MP
    assert bomb.stat().st_size < 200_000

    def decode(*_args, **_kwargs):
        raise AssertionError("the image must not be decoded")

    monkeypatch.setattr(cv2, "imread", decode)
    with pytest.raises(RuntimeError, match="too large"):
        scan_service.run_local_ocr(_scan(bomb), _template())


def test_opencv_pixel_cap_is_configured():
    from modules.scoring.score_sheets import scan_service

    assert int(os.environ["OPENCV_IO_MAX_IMAGE_PIXELS"]) == scan_service.MAX_SCAN_PIXELS


def test_pdf_rasterization_is_bounded(tmp_path, monkeypatch):
    from modules.scoring.score_sheets import scan_service

    calls = []

    def fake_run(args, **_kwargs):
        calls.append(args)
        Image.new("L", (10, 10)).save(tmp_path / "page.png")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(scan_service.subprocess, "run", fake_run)
    scan_service._rasterize(tmp_path / "sheet.pdf", tmp_path)
    args = calls[0]
    assert args[args.index("-r") + 1] == "150"
    assert int(args[args.index("-scale-to") + 1]) <= 3000


def test_normal_score_sheet_passes_the_size_check(tmp_path):
    from modules.scoring.score_sheets import scan_service

    path = tmp_path / "sheet.png"
    Image.new("L", (2480, 3508)).save(path)  # A4 at 300 dpi
    scan_service.assert_scan_dimensions(path)
