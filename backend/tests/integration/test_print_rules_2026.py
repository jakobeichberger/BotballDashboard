"""3D-print rules of Game Review v1.4: material/color, build volume, part limit, STL flag."""

import struct

import pytest

from modules.printing import rules


def _stl(points: list[tuple[float, float, float]]) -> bytes:
    """Binary STL with one triangle per three points."""
    triangles = [points[i : i + 3] for i in range(0, len(points), 3)]
    body = b"".join(
        struct.pack("<3f", 0, 0, 0)
        + b"".join(struct.pack("<3f", *p) for p in tri)
        + struct.pack("<H", 0)
        for tri in triangles
    )
    return b"binary".ljust(80, b" ") + struct.pack("<I", len(triangles)) + body


BOX_200 = _stl([(0, 0, 0), (200, 10, 0), (5, 180, 240)])  # 200 × 180 × 240 mm
TOO_BIG = _stl([(0, 0, 0), (230, 10, 0), (5, 230, 100)])  # 230 × 230 × 100 mm


class TestRules:
    def test_greyscale(self):
        assert rules.is_greyscale("Black") is True
        assert rules.is_greyscale("hellgrau") is True
        assert rules.is_greyscale("#808080") is True
        assert rules.is_greyscale("#7f8082") is True  # within tolerance
        assert rules.is_greyscale("#ff0000") is False
        assert rules.is_greyscale("red") is False
        assert rules.is_greyscale(None) is None

    def test_build_volume_allows_turning_the_part(self):
        assert rules.fits_build_volume((250, 220, 220))
        assert rules.fits_build_volume((220, 250, 100))
        assert rules.fits_build_volume((230, 100, 100))  # 230 mm fits along z (250)
        assert not rules.fits_build_volume((230, 230, 100))
        assert not rules.fits_build_volume((260, 10, 10))

    def test_bounding_box_binary_and_ascii(self, tmp_path):
        binary = tmp_path / "a.stl"
        binary.write_bytes(BOX_200)
        assert rules.stl_bounding_box(binary) == pytest.approx((200, 180, 240))
        ascii_file = tmp_path / "b.stl"
        ascii_file.write_bytes(
            b"solid x\nfacet normal 0 0 1\nouter loop\nvertex -5 0 0\nvertex 5 20 0\n"
            b"vertex 0 0 30.5\nendloop\nendfacet\nendsolid x\n"
        )
        assert rules.stl_bounding_box(ascii_file) == pytest.approx((10, 20, 30.5))
        empty = tmp_path / "c.stl"
        empty.write_bytes(b"solid x\nendsolid x\n")
        assert rules.stl_bounding_box(empty) is None

    def test_job_warnings(self):
        assert rules.job_warnings("PLA", "black", (100, 100, 100)) == []
        assert rules.job_warnings("petg", None, None) == []
        assert rules.job_warnings("ABS", "orange", (300, 10, 10)) == [
            "material_not_allowed",
            "color_not_greyscale",
            "exceeds_build_volume",
        ]


async def _job(client, headers, team, season, **extra):
    resp = await client.post(
        "/api/printing/jobs",
        headers=headers,
        json={"team_id": team.id, "season_id": season.id, "file_name": "part.stl", **extra},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _upload(client, headers, job_id, content):
    return await client.post(
        f"/api/printing/jobs/{job_id}/file",
        headers=headers,
        files={"file": ("part.stl", content, "application/octet-stream")},
    )


@pytest.mark.asyncio
async def test_upload_measures_the_stl_and_warns(client, auth_headers, team, season):
    job = await _job(client, auth_headers, team, season, material="PLA", color="Grau")
    assert job["rule_warnings"] == []
    ok = await _upload(client, auth_headers, job["id"], BOX_200)
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert (body["bbox_x_mm"], body["bbox_y_mm"], body["bbox_z_mm"]) == pytest.approx(
        (200, 180, 240)
    )
    assert body["rule_warnings"] == []

    big = await _job(client, auth_headers, team, season, material="ABS", color="#ff8800")
    assert big["rule_warnings"] == ["material_not_allowed", "color_not_greyscale"]
    body = (await _upload(client, auth_headers, big["id"], TOO_BIG)).json()
    assert "exceeds_build_volume" in body["rule_warnings"]


@pytest.mark.asyncio
async def test_robot_parts_are_counted_against_six(client, auth_headers, team, season, db):
    from modules.printing.models import TeamSeasonPrintQuota

    # Room in the print-service quota, so only the game-review limit matters.
    db.add(TeamSeasonPrintQuota(team_id=team.id, season_id=season.id, max_parts=50))
    await db.commit()
    url = f"/api/printing/teams/{team.id}/seasons/{season.id}/robot-parts"
    first = await _job(client, auth_headers, team, season, part_count=4)
    await _job(client, auth_headers, team, season, part_count=2, purpose="spare")
    await _job(client, auth_headers, team, season, part_count=5, purpose="jig")
    summary = (await client.get(url, headers=auth_headers)).json()
    assert summary == {
        "team_id": team.id,
        "season_id": season.id,
        "used": 4,
        "limit": 6,
        "over_limit": False,
        "stl_missing": 1,
    }
    extra = await _job(client, auth_headers, team, season, part_count=3)
    summary = (await client.get(url, headers=auth_headers)).json()
    assert (summary["used"], summary["over_limit"]) == (7, True)

    # A rejected job does not count; the STL flag is set by the organisers.
    await client.put(
        f"/api/printing/jobs/{extra['id']}/reject", headers=auth_headers, json={"reason": "x"}
    )
    resp = await client.patch(
        f"/api/printing/jobs/{first['id']}", headers=auth_headers, json={"stl_submitted": True}
    )
    assert resp.json()["stl_submitted"] is True
    await db.flush()  # the test session does not autoflush between requests
    summary = (await client.get(url, headers=auth_headers)).json()
    assert (summary["used"], summary["over_limit"], summary["stl_missing"]) == (4, False, 0)
