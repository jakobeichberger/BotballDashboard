"""Small dependency-free Prometheus exposition for core API signals."""

from collections import defaultdict
from time import perf_counter

from fastapi import Request

REQUESTS: defaultdict[tuple[str, str, int], int] = defaultdict(int)
DURATION: defaultdict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])


async def observe_request(request: Request, call_next):
    started = perf_counter()
    response = await call_next(request)
    route = request.scope.get("route")
    # Fall back to a constant, never the raw URL: FastAPI only sets `route` on
    # a match, so using request.url.path would let anyone add an unbounded
    # number of keys (and Prometheus series) just by requesting /api/&lt;random&gt;.
    path = getattr(route, "path", "<unmatched>")
    key = (request.method, path)
    REQUESTS[(request.method, path, response.status_code)] += 1
    DURATION[key][0] += 1
    DURATION[key][1] += perf_counter() - started
    return response


def render_metrics() -> str:
    lines = [
        "# HELP botball_http_requests_total HTTP requests by method, route and status.",
        "# TYPE botball_http_requests_total counter",
    ]
    for (method, path, status), count in sorted(REQUESTS.items()):
        lines.append(
            "botball_http_requests_total"
            f'{{method="{method}",route="{path}",status="{status}"}} {count}'
        )
    lines.extend(
        [
            "# HELP botball_http_request_duration_seconds HTTP request duration summary.",
            "# TYPE botball_http_request_duration_seconds summary",
        ]
    )
    for (method, path), (duration_count, total) in sorted(DURATION.items()):
        labels = f'method="{method}",route="{path}"'
        lines.append(
            f"botball_http_request_duration_seconds_count{{{labels}}} {int(duration_count)}"
        )
        lines.append(f"botball_http_request_duration_seconds_sum{{{labels}}} {total:.6f}")
    return "\n".join(lines) + "\n"
