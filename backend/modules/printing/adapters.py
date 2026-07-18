"""Concrete status adapters for OctoPrint and Bambu Lab LAN printers."""

import json
import ssl
import threading
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class PrinterStatus:
    online: bool
    state: str
    progress: float | None = None
    message: str | None = None


class OctoPrintAdapter:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {"X-Api-Key": api_key}

    def poll(self) -> PrinterStatus:
        with httpx.Client(timeout=8) as client:
            response = client.get(f"{self.base_url}/api/job", headers=self.headers)
            response.raise_for_status()
            data = response.json()
        state = str(data.get("state", "unknown")).lower()
        completion = data.get("progress", {}).get("completion")
        mapped = {
            "printing": "printing",
            "paused": "paused",
            "error": "failed",
            "operational": "idle",
            "offline": "offline",
        }.get(state, "idle")
        return PrinterStatus(
            online=state != "offline",
            state=mapped,
            progress=float(completion) if completion is not None else None,
            message=data.get("state"),
        )


class BambuLanAdapter:
    """Read one encrypted MQTT report from a Bambu printer on the local network."""

    def __init__(self, host: str, access_code: str, serial: str):
        self.host = host.removeprefix("mqtts://").split(":", 1)[0]
        self.access_code = access_code
        self.serial = serial

    def poll(self) -> PrinterStatus:
        import paho.mqtt.client as mqtt

        result: dict = {}
        received = threading.Event()
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.username_pw_set("bblp", self.access_code)
        client.tls_set(cert_reqs=ssl.CERT_NONE)
        client.tls_insecure_set(True)

        def on_connect(client, userdata, flags, reason_code, properties):
            client.subscribe(f"device/{self.serial}/report")
            client.publish(
                f"device/{self.serial}/request",
                json.dumps({"pushing": {"sequence_id": "0", "command": "pushall"}}),
            )

        def on_message(client, userdata, message):
            try:
                result.update(json.loads(message.payload).get("print", {}))
            finally:
                received.set()

        client.on_connect = on_connect
        client.on_message = on_message
        client.connect(self.host, 8883, keepalive=10)
        client.loop_start()
        try:
            if not received.wait(8):
                return PrinterStatus(False, "offline", message="Bambu MQTT timeout")
        finally:
            client.loop_stop()
            client.disconnect()
        raw = str(result.get("gcode_state", "IDLE")).upper()
        state = {
            "RUNNING": "printing",
            "PAUSE": "paused",
            "FINISH": "completed",
            "FAILED": "failed",
            "IDLE": "idle",
        }.get(raw, "idle")
        progress = result.get("mc_percent")
        return PrinterStatus(True, state, float(progress) if progress is not None else None, raw)


def poll_printer(printer_type: str, api_url: str, api_key: str, device_id: str | None):
    if printer_type == "octoprint":
        return OctoPrintAdapter(api_url, api_key).poll()
    if printer_type == "bambu":
        if not device_id:
            raise ValueError("Bambu printer requires a device serial")
        return BambuLanAdapter(api_url, api_key, device_id).poll()
    raise ValueError(f"Unsupported printer adapter: {printer_type}")
