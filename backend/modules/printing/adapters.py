"""Concrete status adapters for OctoPrint and Bambu Lab LAN printers.

Every adapter reduces its printer's report to a PrinterStatus with one of the
normalised states idle | printing | paused | completed | failed | offline.
"completed" means the printer says its last print finished successfully; which
job that was is decided by service.apply_printer_status, not here.
"""

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
    remaining_seconds: int | None = None
    error: str | None = None


# OctoPrint reports its state as display text ("Printing from SD", "Offline
# after error: ..."), so match on the leading word(s).
_OCTOPRINT_STATES: tuple[tuple[str, str], ...] = (
    ("offline after error", "failed"),
    ("error", "failed"),
    ("offline", "offline"),
    ("closed", "offline"),
    ("printing", "printing"),
    ("starting", "printing"),
    ("finishing", "printing"),
    ("resuming", "printing"),
    ("cancelling", "printing"),
    ("pausing", "paused"),
    ("paused", "paused"),
    ("operational", "idle"),
)


class OctoPrintAdapter:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {"X-Api-Key": api_key}

    def poll(self) -> PrinterStatus:
        with httpx.Client(timeout=8) as client:
            response = client.get(f"{self.base_url}/api/job", headers=self.headers)
            response.raise_for_status()
            data = response.json()
        return self.parse(data)

    @staticmethod
    def parse(data: dict) -> PrinterStatus:
        raw = str(data.get("state", "unknown"))
        lowered = raw.lower()
        state = next(
            (mapped for key, mapped in _OCTOPRINT_STATES if lowered.startswith(key)), "idle"
        )
        progress_data = data.get("progress") or {}
        completion = progress_data.get("completion")
        progress = float(completion) if completion is not None else None
        # After a print OctoPrint goes back to "Operational" but keeps the last
        # job's completion; 100 % there means the print finished.
        if state == "idle" and progress is not None and progress >= 100:
            state = "completed"
        left = progress_data.get("printTimeLeft")
        error = data.get("error") or (raw if state == "failed" else None)
        return PrinterStatus(
            online=state != "offline",
            state=state,
            progress=progress,
            message=raw,
            remaining_seconds=int(left) if left is not None else None,
            error=str(error) if error else None,
        )

    def cancel(self) -> str:
        """Stop the running print (POST /api/job {"command": "cancel"}).

        OctoPrint answers 204 on success and 409 when nothing is printing,
        which counts as done here: there is nothing left to stop.
        """
        with httpx.Client(timeout=8) as client:
            response = client.post(
                f"{self.base_url}/api/job", headers=self.headers, json={"command": "cancel"}
            )
        if response.status_code == 409:
            return "No active print on the printer"
        response.raise_for_status()
        return "Cancel command accepted by OctoPrint"


class BambuLanAdapter:
    """Read one encrypted MQTT report from a Bambu printer on the local network."""

    def __init__(self, host: str, access_code: str, serial: str):
        self.host = host.removeprefix("mqtts://").split(":", 1)[0]
        self.access_code = access_code
        self.serial = serial

    def _client(self):
        import paho.mqtt.client as mqtt

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.username_pw_set("bblp", self.access_code)
        client.tls_set(cert_reqs=ssl.CERT_NONE)
        client.tls_insecure_set(True)
        return client

    def cancel(self) -> str:
        """Send the MQTT "stop" command, which aborts the current print."""
        connected = threading.Event()
        client = self._client()
        client.on_connect = lambda *args: connected.set()
        client.connect(self.host, 8883, keepalive=10)
        client.loop_start()
        try:
            if not connected.wait(8):
                raise TimeoutError("Bambu MQTT connection timed out")
            info = client.publish(
                f"device/{self.serial}/request",
                json.dumps({"print": {"sequence_id": "0", "command": "stop", "param": ""}}),
                qos=1,
            )
            info.wait_for_publish(timeout=8)
            if not info.is_published():
                raise TimeoutError("Bambu printer did not acknowledge the stop command")
        finally:
            client.loop_stop()
            client.disconnect()
        return "Stop command sent to the Bambu printer"

    def poll(self) -> PrinterStatus:
        result: dict = {}
        received = threading.Event()
        client = self._client()

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
        return self.parse(result)

    @staticmethod
    def parse(report: dict) -> PrinterStatus:
        raw = str(report.get("gcode_state", "IDLE")).upper()
        state = {
            "PREPARE": "printing",
            "SLICING": "printing",
            "RUNNING": "printing",
            "PAUSE": "paused",
            "FINISH": "completed",
            "FAILED": "failed",
            "IDLE": "idle",
        }.get(raw, "idle")
        progress = report.get("mc_percent")
        remaining_minutes = report.get("mc_remaining_time")
        error_code = report.get("print_error")
        error = None
        if error_code:
            # Bambu error codes are 32-bit ints, documented as 8 hex digits.
            try:
                error = f"Bambu error {int(error_code):08X}"
            except TypeError, ValueError:
                error = f"Bambu error {error_code}"
        elif state == "failed":
            error = "Print failed on the printer"
        return PrinterStatus(
            online=True,
            state=state,
            progress=float(progress) if progress is not None else None,
            message=raw,
            remaining_seconds=int(remaining_minutes) * 60
            if remaining_minutes is not None
            else None,
            error=error,
        )


def poll_printer(printer_type: str, api_url: str, api_key: str, device_id: str | None):
    if printer_type == "octoprint":
        return OctoPrintAdapter(api_url, api_key).poll()
    if printer_type == "bambu":
        if not device_id:
            raise ValueError("Bambu printer requires a device serial")
        return BambuLanAdapter(api_url, api_key, device_id).poll()
    raise ValueError(f"Unsupported printer adapter: {printer_type}")


def cancel_printer_job(printer_type: str, api_url: str, api_key: str, device_id: str | None) -> str:
    """Abort whatever the printer is printing; returns the printer's answer.

    Raises on connection or protocol errors so the caller can report them.
    """
    if printer_type == "octoprint":
        return OctoPrintAdapter(api_url, api_key).cancel()
    if printer_type == "bambu":
        if not device_id:
            raise ValueError("Bambu printer requires a device serial")
        return BambuLanAdapter(api_url, api_key, device_id).cancel()
    raise ValueError(f"Unsupported printer adapter: {printer_type}")
