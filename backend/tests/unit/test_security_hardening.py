"""Outbound requests from user input (security review 2026-09, #4 and #7).

4.  Push subscription endpoints were fetched server-side without any check (SSRF).
7.  reportlab parsed user text as markup (<img src> fetched URLs and local files).
"""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO

import pytest
from PIL import Image
from pydantic import ValidationError

# ── 4. Push endpoints ─────────────────────────────────────────────────────────


def _subscription(endpoint: str):
    from modules.auth.schemas import PushSubscriptionCreate

    return PushSubscriptionCreate(endpoint=endpoint, p256dh="key", auth="auth")


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://fcm.googleapis.com/fcm/send/abc:def",
        "https://updates.push.services.mozilla.com/wpush/v2/gAAAA",
        "https://wns2-par02p.notify.windows.com/w/?token=BQYAAA",
        "https://web.push.apple.com/QGuQyavXutnMH",
    ],
)
def test_real_push_services_are_accepted(endpoint):
    assert _subscription(endpoint).endpoint == endpoint


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://127.0.0.1:8000/internal/admin",
        "http://fcm.googleapis.com/fcm/send/x",
        "https://127.0.0.1/x",
        "https://10.0.0.5/x",
        "https://[::1]/x",
        "https://169.254.169.254/latest/meta-data",
        "https://evil.example.com/fcm.googleapis.com",
        "https://fcm.googleapis.com.evil.example/x",
        "https://fcm.googleapis.com:8443/x",
        "https://user@fcm.googleapis.com/x",
        "https://localhost/x",
        "fcm.googleapis.com/fcm/send/x",
    ],
)
def test_other_push_endpoints_are_refused(endpoint):
    with pytest.raises(ValidationError):
        _subscription(endpoint)


@pytest.mark.asyncio
async def test_stored_internal_endpoint_is_never_contacted(monkeypatch):
    """Subscriptions saved before the check existed are dropped, not fetched."""
    import pywebpush

    from core import notifications

    hits: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            hits.append(self.path)
            self.send_response(201)
            self.end_headers()

        def log_message(self, *_args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(notifications.settings, "vapid_private_key", "configured")
    sent: list[str] = []
    monkeypatch.setattr(pywebpush, "webpush", lambda **kw: sent.append(kw))
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}/internal/admin"
        status = await notifications.send_push_notification(endpoint, "p", "a", "t", "b")
    finally:
        server.shutdown()
    assert status == "gone"
    assert hits == [] and sent == []


# ── 7. reportlab markup ───────────────────────────────────────────────────────


@pytest.fixture
def image_server(tmp_path):
    hits: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            hits.append(self.path)
            buf = BytesIO()
            Image.new("RGB", (2, 2)).save(buf, "PNG")
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            self.wfile.write(buf.getvalue())

        def log_message(self, *_args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/s", hits
    server.shutdown()


def _img(src: str) -> str:
    return f'<img src="{src}" width="1" height="1"/>'


def test_pdf_exports_never_fetch_images_from_user_text(tmp_path, image_server):
    from modules.exports import pdf_builder

    url, hits = image_server
    local = tmp_path / "secret.png"
    Image.new("RGB", (4, 4), "red").save(local)
    pdfs = [
        pdf_builder.build_paper_review_pdf(
            _img(url),
            [{"team_id": "t", "title": _img(str(local)), "status": "submitted"}],
            {"t": "Team"},
        ),
        pdf_builder.build_print_report_pdf(
            "S",
            [{"team_id": "t", "file_name": _img(url), "status": "queued"}],
            {"t": "Team"},
            {},
        ),
        pdf_builder.build_ranking_pdf(_img(url), _img(str(local)), [], {}),
        pdf_builder.build_overall_ranking_pdf(
            _img(url),
            "<b>unclosed",
            [{"rank": 1, "team_name": "T", "category": _img(str(local))}],
        ),
    ]
    assert hits == []
    for pdf in pdfs:
        assert pdf.startswith(b"%PDF")
        assert b"/Subtype /Image" not in pdf


def test_team_report_title_is_escaped_once():
    from modules.exports import pdf_builder

    pdf = pdf_builder.build_team_report_pdf({"name": "A & B <Robotics>", "school": "HTL <1>"}, [])
    assert pdf.startswith(b"%PDF")
