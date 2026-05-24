"""Capture tools: launch a target with RenderDoc injected, inject into running PIDs, trigger frame captures."""

from __future__ import annotations

import os
import time

from mcp.server.fastmcp import FastMCP

from renderdoc_mcp.session import get_session
from renderdoc_mcp.util import rd, to_json, make_error


_CLIENT_NAME = "renderdoc-mcp"


def _result_to_dict(res) -> dict:
    return {"ok": bool(res.OK()), "code": str(res.code), "message": str(res.Message())}


def _drive_target_control(ctrl, timeout_s: float, expected_captures: int) -> dict:
    deadline = time.monotonic() + timeout_s
    captures: list[dict] = []
    last_api = ""
    last_busy = ""
    while time.monotonic() < deadline and ctrl.Connected():
        msg = ctrl.ReceiveMessage(None)
        t = msg.type
        if t == rd.TargetControlMessageType.NewCapture:
            nc = msg.newCapture
            captures.append({
                "path": str(nc.path),
                "frame_number": int(nc.frameNumber),
                "byte_size": int(nc.byteSize),
                "api": str(nc.api),
                "capture_id": int(nc.captureId),
                "local": bool(nc.local),
                "timestamp": int(nc.timestamp),
                "title": str(nc.title),
            })
            if expected_captures > 0 and len(captures) >= expected_captures:
                return {"captures": captures, "api": last_api or str(ctrl.GetAPI()), "busy_client": last_busy}
        elif t == rd.TargetControlMessageType.RegisterAPI:
            last_api = str(ctrl.GetAPI())
        elif t == rd.TargetControlMessageType.Busy:
            last_busy = str(ctrl.GetBusyClient())
        elif t == rd.TargetControlMessageType.Disconnected:
            break
        else:
            time.sleep(0.05)
    return {"captures": captures, "api": last_api, "busy_client": last_busy, "timed_out": time.monotonic() >= deadline}


def register(mcp: FastMCP):
    @mcp.tool()
    def launch_and_capture(
        executable: str,
        working_dir: str = "",
        cmdline: str = "",
        wait_seconds_before_capture: float = 3.0,
        capture_timeout_seconds: float = 60.0,
        num_frames: int = 1,
        capture_file_template: str = "",
        hook_into_children: bool = False,
        api_validation: bool = False,
        capture_callstacks: bool = False,
        ref_all_resources: bool = False,
        auto_open: bool = False,
        leave_running: bool = False,
    ) -> str:
        """Launch an executable with RenderDoc injected, trigger a frame capture, return the .rdc path.

        Flow: ExecuteAndInject -> CreateTargetControl -> wait for graphics API to come up ->
        TriggerCapture(num_frames) -> wait for NewCapture message -> return path.

        Args:
            executable: Absolute path to the .exe to launch.
            working_dir: Working directory. Defaults to the directory containing the executable.
            cmdline: Command-line arguments string passed to the app.
            wait_seconds_before_capture: How long to wait after launch before issuing TriggerCapture
                (gives the app time to initialize its rendering API and start presenting frames).
            capture_timeout_seconds: Total wall-clock time to wait for the NewCapture message
                after triggering. If the app never presents, returns with timed_out=True.
            num_frames: Number of consecutive frames to capture (each produces its own .rdc).
            capture_file_template: Optional explicit capture file path template (RenderDoc rules).
                Empty = RenderDoc default location (typically %TEMP%\\RenderDoc\\).
            hook_into_children: If True, RenderDoc also injects into any child processes the app spawns.
            api_validation: Enable graphics API validation layer for the run.
            capture_callstacks: Record callstacks at API call sites (slower, larger captures).
            ref_all_resources: Force-reference every resource each frame (larger but more complete captures).
            auto_open: If True, open the first captured .rdc in the current session for analysis.
            leave_running: If True, do not shut down the TargetControl connection — the target keeps
                running. If False, the connection is closed cleanly after capture (target keeps running
                regardless — Shutdown only affects the control channel, not the target process).
        """
        if not os.path.isfile(executable):
            return to_json(make_error(f"Executable not found: {executable}", "API_ERROR"))

        opts = rd.GetDefaultCaptureOptions()
        opts.hookIntoChildren = bool(hook_into_children)
        opts.apiValidation = bool(api_validation)
        opts.captureCallstacks = bool(capture_callstacks)
        opts.refAllResources = bool(ref_all_resources)

        exec_result = rd.ExecuteAndInject(
            executable,
            working_dir or "",
            cmdline or "",
            [],
            capture_file_template or "",
            opts,
            False,
        )
        if not exec_result.result.OK():
            return to_json(make_error(
                f"ExecuteAndInject failed: {exec_result.result.Message()}",
                str(exec_result.result.code),
            ))
        ident = int(exec_result.ident)
        if ident <= 0:
            return to_json(make_error("ExecuteAndInject returned no ident (cannot control target)", "API_ERROR"))

        if wait_seconds_before_capture > 0:
            time.sleep(wait_seconds_before_capture)

        ctrl = rd.CreateTargetControl("", ident, _CLIENT_NAME, True)
        if ctrl is None:
            return to_json(make_error(f"CreateTargetControl failed for ident={ident}", "API_ERROR"))

        try:
            settle_deadline = time.monotonic() + min(5.0, capture_timeout_seconds)
            while time.monotonic() < settle_deadline and ctrl.Connected() and not str(ctrl.GetAPI()):
                ctrl.ReceiveMessage(None)
                time.sleep(0.05)

            ctrl.TriggerCapture(int(num_frames))
            drive = _drive_target_control(ctrl, capture_timeout_seconds, expected_captures=int(num_frames))
        finally:
            if not leave_running:
                try:
                    ctrl.Shutdown()
                except Exception:
                    pass

        result: dict = {
            "ident": ident,
            "executable": executable,
            "pid": None,
            "api": drive.get("api", ""),
            "captures": drive.get("captures", []),
            "timed_out": drive.get("timed_out", False),
        }
        if not result["captures"]:
            result["error"] = "No NewCapture message received before timeout"

        if auto_open and result["captures"]:
            first_path = result["captures"][0]["path"]
            if os.path.isfile(first_path):
                opened = get_session().open(first_path)
                result["opened"] = opened
            else:
                result["open_skipped_reason"] = f"Capture path not accessible locally: {first_path}"

        return to_json(result)

    @mcp.tool()
    def inject_into_running_process(
        pid: int,
        wait_seconds_before_capture: float = 1.0,
        capture_timeout_seconds: float = 60.0,
        num_frames: int = 1,
        capture_file_template: str = "",
        hook_into_children: bool = False,
        api_validation: bool = False,
        capture_callstacks: bool = False,
        ref_all_resources: bool = False,
        auto_open: bool = False,
        leave_running: bool = False,
    ) -> str:
        """Inject RenderDoc into an already-running process by PID and trigger a capture.

        Note: on Windows this requires the calling process (this MCP server) to have
        sufficient privileges to inject into the target. If injection fails with an
        access error, the user may need to run the host (Claude Code) as administrator.

        Args mirror launch_and_capture except no executable/working_dir/cmdline.
        """
        opts = rd.GetDefaultCaptureOptions()
        opts.hookIntoChildren = bool(hook_into_children)
        opts.apiValidation = bool(api_validation)
        opts.captureCallstacks = bool(capture_callstacks)
        opts.refAllResources = bool(ref_all_resources)

        exec_result = rd.InjectIntoProcess(
            int(pid),
            [],
            capture_file_template or "",
            opts,
            False,
        )
        if not exec_result.result.OK():
            return to_json(make_error(
                f"InjectIntoProcess failed: {exec_result.result.Message()}",
                str(exec_result.result.code),
            ))
        ident = int(exec_result.ident)
        if ident <= 0:
            return to_json(make_error("InjectIntoProcess returned no ident", "API_ERROR"))

        if wait_seconds_before_capture > 0:
            time.sleep(wait_seconds_before_capture)

        ctrl = rd.CreateTargetControl("", ident, _CLIENT_NAME, True)
        if ctrl is None:
            return to_json(make_error(f"CreateTargetControl failed for ident={ident}", "API_ERROR"))

        try:
            ctrl.TriggerCapture(int(num_frames))
            drive = _drive_target_control(ctrl, capture_timeout_seconds, expected_captures=int(num_frames))
        finally:
            if not leave_running:
                try:
                    ctrl.Shutdown()
                except Exception:
                    pass

        result: dict = {
            "ident": ident,
            "pid": int(pid),
            "api": drive.get("api", ""),
            "captures": drive.get("captures", []),
            "timed_out": drive.get("timed_out", False),
        }
        if not result["captures"]:
            result["error"] = "No NewCapture message received before timeout"
        if auto_open and result["captures"]:
            first_path = result["captures"][0]["path"]
            if os.path.isfile(first_path):
                result["opened"] = get_session().open(first_path)

        return to_json(result)

    @mcp.tool()
    def list_capture_targets(url: str = "") -> str:
        """Enumerate processes that currently have RenderDoc injected and are reachable.

        Args:
            url: Host URL to query. Empty = local machine via TCP enumeration.

        Returns a list of {ident, pid, target, api, busy_client} entries.
        """
        targets: list[dict] = []
        seen: set[int] = set()
        next_ident = 0
        while True:
            next_ident = int(rd.EnumerateRemoteTargets(url or "", next_ident))
            if next_ident == 0 or next_ident in seen:
                break
            seen.add(next_ident)
            ctrl = rd.CreateTargetControl(url or "", next_ident, _CLIENT_NAME, False)
            if ctrl is None:
                targets.append({"ident": next_ident, "error": "could not connect"})
                continue
            try:
                ctrl.ReceiveMessage(None)
                targets.append({
                    "ident": next_ident,
                    "pid": int(ctrl.GetPID()),
                    "target": str(ctrl.GetTarget()),
                    "api": str(ctrl.GetAPI()),
                    "busy_client": str(ctrl.GetBusyClient()),
                })
            finally:
                ctrl.Shutdown()
        return to_json({"url": url or "localhost", "targets": targets})

    @mcp.tool()
    def trigger_capture_on_target(
        ident: int,
        url: str = "",
        num_frames: int = 1,
        capture_timeout_seconds: float = 60.0,
        force_connection: bool = False,
        auto_open: bool = False,
        leave_running: bool = False,
    ) -> str:
        """Trigger a frame capture on an already-injected target identified by ident.

        Use list_capture_targets first to discover idents.
        """
        ctrl = rd.CreateTargetControl(url or "", int(ident), _CLIENT_NAME, bool(force_connection))
        if ctrl is None:
            return to_json(make_error(
                f"CreateTargetControl failed for ident={ident} (busy or unreachable; try force_connection=True)",
                "API_ERROR",
            ))
        try:
            ctrl.TriggerCapture(int(num_frames))
            drive = _drive_target_control(ctrl, capture_timeout_seconds, expected_captures=int(num_frames))
        finally:
            if not leave_running:
                try:
                    ctrl.Shutdown()
                except Exception:
                    pass

        result: dict = {
            "ident": int(ident),
            "url": url or "localhost",
            "api": drive.get("api", ""),
            "captures": drive.get("captures", []),
            "timed_out": drive.get("timed_out", False),
        }
        if not result["captures"]:
            result["error"] = "No NewCapture message received before timeout"
        if auto_open and result["captures"]:
            first_path = result["captures"][0]["path"]
            if os.path.isfile(first_path):
                result["opened"] = get_session().open(first_path)
        return to_json(result)
