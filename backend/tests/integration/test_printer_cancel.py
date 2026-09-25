"""Cancelling a running print on the printer, and the print upload size limit."""

import json

import httpx
import pytest

from core.config import get_settings
from modules.printing import adapters, service
from modules.printing.models import Printer, PrintJob


class TestOctoPrintCancel:
    def _patch_client(self, monkeypatch, status_code: int, seen: list):
        real_client = httpx.Client

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append((request.method, str(request.url), request.headers, request.content))
            return httpx.Response(status_code)

        monkeypatch.setattr(
            adapters.httpx,
            "Client",
            lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
        )

    def test_posts_cancel_command(self, monkeypatch):
        seen: list = []
        self._patch_client(monkeypatch, 204, seen)
        message = adapters.OctoPrintAdapter("http://octopi.local/", "KEY").cancel()
        assert "accepted" in message
        method, url, headers, body = seen[0]
        assert (method, url) == ("POST", "http://octopi.local/api/job")
        assert headers["X-Api-Key"] == "KEY"
        assert json.loads(body) == {"command": "cancel"}

    def test_nothing_printing_is_not_an_error(self, monkeypatch):
        self._patch_client(monkeypatch, 409, [])
        assert "No active print" in adapters.OctoPrintAdapter("http://o", "k").cancel()

    def test_server_error_raises(self, monkeypatch):
        self._patch_client(monkeypatch, 500, [])
        with pytest.raises(httpx.HTTPStatusError):
            adapters.OctoPrintAdapter("http://o", "k").cancel()


class _FakeInfo:
    def __init__(self, published: bool):
        self._published = published

    def wait_for_publish(self, timeout=None):
        return None

    def is_published(self):
        return self._published


class _FakeMqttClient:
    instances: list = []
    published = True

    def __init__(self, *args, **kwargs):
        self.messages: list = []
        self.on_connect = None
        _FakeMqttClient.instances.append(self)

    def username_pw_set(self, user, password):
        self.credentials = (user, password)

    def tls_set(self, **kwargs):
        pass

    def tls_insecure_set(self, value):
        pass

    def connect(self, host, port, keepalive=60):
        self.address = (host, port)

    def loop_start(self):
        if self.on_connect:
            self.on_connect(self, None, None, 0, None)

    def loop_stop(self):
        pass

    def disconnect(self):
        pass

    def publish(self, topic, payload, qos=0):
        self.messages.append((topic, json.loads(payload), qos))
        return _FakeInfo(_FakeMqttClient.published)


class TestBambuCancel:
    @pytest.fixture(autouse=True)
    def fake_mqtt(self, monkeypatch):
        import paho.mqtt.client as mqtt

        _FakeMqttClient.instances = []
        _FakeMqttClient.published = True
        monkeypatch.setattr(mqtt, "Client", _FakeMqttClient)

    def test_sends_stop_command(self):
        message = adapters.BambuLanAdapter("mqtts://192.168.1.5:8883", "12345678", "SN1").cancel()
        assert "Stop command" in message
        client = _FakeMqttClient.instances[0]
        assert client.address == ("192.168.1.5", 8883)
        assert client.credentials == ("bblp", "12345678")
        topic, payload, qos = client.messages[0]
        assert topic == "device/SN1/request"
        assert payload == {"print": {"sequence_id": "0", "command": "stop", "param": ""}}
        assert qos == 1

    def test_unacknowledged_stop_raises(self):
        _FakeMqttClient.published = False
        with pytest.raises(TimeoutError):
            adapters.BambuLanAdapter("192.168.1.5", "code", "SN1").cancel()

    def test_dispatch_requires_serial(self):
        with pytest.raises(ValueError):
            adapters.cancel_printer_job("bambu", "host", "code", None)
        with pytest.raises(ValueError):
            adapters.cancel_printer_job("generic", "host", "code", None)


async def _printing_job(db, team, season, printer_type="octoprint", status="printing"):
    printer = Printer(
        name=f"{printer_type}-1",
        printer_type=printer_type,
        api_url=None if printer_type == "generic" else "http://printer.local",
        device_id="SN1" if printer_type == "bambu" else None,
    )
    db.add(printer)
    await db.flush()
    from modules.scoring.service import resolve_event

    event = await resolve_event(db, season.id, None)
    job = PrintJob(
        team_id=team.id,
        season_id=season.id,
        event_id=event.id,
        file_name="part.stl",
        status=status,
        printer_id=printer.id,
    )
    db.add(job)
    await db.commit()
    return job


class TestCancelRoute:
    @pytest.fixture
    def calls(self, monkeypatch):
        calls: list = []

        def fake_cancel(printer_type, api_url, api_key, device_id):
            calls.append((printer_type, api_url, device_id))
            return "Cancel command accepted by OctoPrint"

        monkeypatch.setattr(service, "cancel_printer_job", fake_cancel)
        return calls

    @pytest.mark.asyncio
    async def test_admin_cancel_stops_running_print(
        self, client, db, auth_headers, team, season, calls
    ):
        job = await _printing_job(db, team, season)
        resp = await client.put(f"/api/printing/jobs/{job.id}/cancel", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "cancelled"
        assert data["printer_cancel"] == "sent"
        assert calls == [("octoprint", "http://printer.local", None)]

    @pytest.mark.asyncio
    async def test_printer_failure_still_cancels_in_db(
        self, client, db, auth_headers, team, season, monkeypatch
    ):
        def broken(*args):
            raise httpx.ConnectError("printer unreachable")

        monkeypatch.setattr(service, "cancel_printer_job", broken)
        job = await _printing_job(db, team, season, printer_type="bambu")
        resp = await client.put(f"/api/printing/jobs/{job.id}/cancel", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"
        assert resp.json()["printer_cancel"] == "failed"
        assert "printer unreachable" in resp.json()["printer_message"]

    @pytest.mark.asyncio
    async def test_not_printing_does_not_touch_printer(
        self, client, db, auth_headers, team, season, calls
    ):
        job = await _printing_job(db, team, season, status="queued")
        resp = await client.put(f"/api/printing/jobs/{job.id}/cancel", headers=auth_headers)
        assert resp.json()["printer_cancel"] == "not_applicable"
        assert calls == []

    @pytest.mark.asyncio
    async def test_generic_printer_is_manual(self, client, db, auth_headers, team, season, calls):
        job = await _printing_job(db, team, season, printer_type="generic")
        resp = await client.put(f"/api/printing/jobs/{job.id}/cancel", headers=auth_headers)
        assert resp.json()["status"] == "cancelled"
        assert resp.json()["printer_cancel"] == "not_applicable"
        assert "Manually operated" in resp.json()["printer_message"]
        assert calls == []


class TestPrintUploadLimit:
    def test_setting_default(self):
        assert get_settings().print_upload_max_mb == 100

    @pytest.mark.asyncio
    async def test_print_route_has_its_own_body_limit(
        self, client, db, auth_headers, team, season, monkeypatch
    ):
        settings = get_settings()
        monkeypatch.setattr(settings, "max_upload_size_mb", 0)
        monkeypatch.setattr(settings, "print_upload_max_mb", 3)
        job = await _printing_job(db, team, season, status="pending")
        body = b"solid part\n" + b" " * (2 * 1024 * 1024) + b"\nendsolid part\n"

        paper = await client.post(
            "/api/papers/some-id/upload",
            headers=auth_headers,
            files={"file": ("p.pdf", body, "application/pdf")},
        )
        assert paper.status_code == 413

        upload = await client.post(
            f"/api/printing/jobs/{job.id}/file",
            headers=auth_headers,
            files={"file": ("part.stl", body, "application/octet-stream")},
        )
        assert upload.status_code == 200, upload.text

        monkeypatch.setattr(settings, "print_upload_max_mb", 1)
        too_big = await client.post(
            f"/api/printing/jobs/{job.id}/file",
            headers=auth_headers,
            files={"file": ("part.stl", body, "application/octet-stream")},
        )
        assert too_big.status_code in (413, 422)
