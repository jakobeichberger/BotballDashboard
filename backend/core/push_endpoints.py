"""Which Web Push endpoints the server may contact.

A push subscription's endpoint is a URL the browser hands us; the server
later POSTs to it (core.notifications.send_push_notification). Accepting any
URL let every signed-in user make the backend and the worker send requests to
internal addresses (SSRF: Redis, PostgreSQL, the metrics endpoint, cloud
metadata services). Real endpoints always point to one of the browser vendors'
push services over HTTPS, so only those are accepted.
"""

import ipaddress
from urllib.parse import urlsplit

#: Push services of the browsers in use (Chrome/Edge/Opera/Brave/Samsung via
#: FCM, Firefox via Mozilla autopush, Edge on Windows via WNS, Safari via APNs).
PUSH_SERVICE_HOSTS = frozenset({"fcm.googleapis.com", "web.push.apple.com"})
PUSH_SERVICE_SUFFIXES = (".push.services.mozilla.com", ".notify.windows.com")

MAX_ENDPOINT_LENGTH = 2048


def push_endpoint_problem(endpoint: str) -> str | None:
    """Why `endpoint` must not be contacted, or None when it is a push service."""
    if len(endpoint) > MAX_ENDPOINT_LENGTH:
        return "Push endpoint is too long"
    try:
        parts = urlsplit(endpoint)
        port = parts.port
    except ValueError:
        return "Push endpoint is not a valid URL"
    if parts.scheme != "https":
        return "Push endpoint must use https"
    if parts.username is not None or parts.password is not None:
        return "Push endpoint must not contain credentials"
    if port not in (None, 443):
        return "Push endpoint must use the default https port"
    host = (parts.hostname or "").rstrip(".").lower()
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        # Push services are addressed by name; an IP literal (loopback, private
        # networks, link-local metadata addresses) never is one.
        return "Push endpoint must not be an IP address"
    if host in PUSH_SERVICE_HOSTS or host.endswith(PUSH_SERVICE_SUFFIXES):
        return None
    return "Push endpoint is not a known push service"
