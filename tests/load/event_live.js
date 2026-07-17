import http from "k6/http";
import ws from "k6/ws";
import { check, sleep } from "k6";

export const options = {
  scenarios: {
    scoring: { executor: "constant-vus", vus: 30, duration: "2m", exec: "score" },
    spectators: { executor: "constant-vus", vus: 200, duration: "2m", exec: "watch" },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<2000"],
    "checks{kind:live_latency}": ["rate>0.99"],
  },
};

const base = __ENV.BASE_URL || "http://localhost:8000/api";
const eventId = __ENV.EVENT_ID;
const eventSlug = __ENV.EVENT_SLUG;
const token = __ENV.ACCESS_TOKEN;
const teamId = __ENV.TEAM_ID;

export function score() {
  const started = Date.now();
  const response = http.post(`${base}/v1/events/${eventId}/matches`, JSON.stringify({
    team_id: teamId,
    raw_scores: {},
    idempotency_key: `${__VU}-${__ITER}-${started}`,
  }), { headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` } });
  check(response, { "score accepted": (item) => item.status === 201 });
  sleep(1);
}

export function watch() {
  const url = base.replace(/^http/, "ws") + `/v1/public/events/${eventSlug}/ws`;
  const started = Date.now();
  const response = ws.connect(url, {}, (socket) => {
    socket.on("message", () => {
      check(Date.now() - started, { "live update below two seconds": (ms) => ms < 2000 }, { kind: "live_latency" });
      socket.close();
    });
    socket.setTimeout(() => socket.close(), 10000);
  });
  check(response, { "websocket upgraded": (item) => item && item.status === 101 });
}
