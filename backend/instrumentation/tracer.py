from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
import threading
import time
import types


@dataclass
class SymbolEvent:
    symbol_key: str
    display_name: str
    file_path: str
    function_name: str
    elapsed_ms: float
    self_time_ms: float
    recursion_depth: int
    had_exception: bool
    exception_type: str | None


@dataclass
class ExternalBucketEvent:
    bucket_name: str
    elapsed_ms: float


@dataclass
class _TraceFrame:
    kind: str
    started_at: float
    file_path: str | None = None
    symbol_key: str | None = None
    display_name: str | None = None
    function_name: str | None = None
    bucket_name: str | None = None
    child_time_ms: float = 0.0
    recursion_depth: int = 1
    had_exception: bool = False
    last_exception_type: str | None = None
    track_external: bool = False


class PythonTracer:
    def __init__(self, project_root: str | Path, collector) -> None:
        self.project_root = Path(project_root).resolve()
        self.collector = collector
        self._thread_stacks: dict[int, list[_TraceFrame]] = {}
        self._enabled = False
        self._instrumentation_root = Path(__file__).resolve().parent
        self._excluded_relative_prefixes = ("backend/instrumentation/",)
        self._callback_guard = threading.local()

    def start(self) -> None:
        if self._enabled:
            return
        self._enabled = True
        sys.setprofile(self._profile)
        threading.setprofile(self._profile)

    def stop(self) -> None:
        sys.setprofile(None)
        threading.setprofile(None)
        self._enabled = False
        self._thread_stacks.clear()

    def _profile(self, frame: types.FrameType, event: str, arg) -> None:  # type: ignore[override]
        if getattr(self._callback_guard, "active", False):
            return
        self._callback_guard.active = True
        callback_started = time.perf_counter()
        should_record_callback = False
        try:
            if event not in {"call", "return", "exception"}:
                return
            thread_id = threading.get_ident()
            stack = self._thread_stacks.setdefault(thread_id, [])

            if event == "call":
                trace_frame = self._classify_frame(frame, stack)
                if trace_frame is not None:
                    stack.append(trace_frame)
                    should_record_callback = True
                return

            if not stack:
                return

            current = stack[-1]
            if event == "exception":
                current.had_exception = True
                exception_type = arg[0] if isinstance(arg, tuple) and arg else None
                current.last_exception_type = getattr(exception_type, "__name__", None)
                should_record_callback = True
                return

            stack.pop()
            elapsed_ms = (time.perf_counter() - current.started_at) * 1000.0
            self_time_ms = max(elapsed_ms - current.child_time_ms, 0.0)
            if stack:
                stack[-1].child_time_ms += elapsed_ms
            should_record_callback = True

            if current.kind == "project" and current.symbol_key and current.file_path and current.display_name and current.function_name:
                self.collector.record_symbol_event(
                    SymbolEvent(
                        symbol_key=current.symbol_key,
                        display_name=current.display_name,
                        file_path=current.file_path,
                        function_name=current.function_name,
                        elapsed_ms=elapsed_ms,
                        self_time_ms=self_time_ms,
                        recursion_depth=current.recursion_depth,
                        had_exception=current.had_exception,
                        exception_type=current.last_exception_type,
                    )
                )
            elif current.kind == "external" and current.track_external and current.bucket_name:
                self.collector.record_external_bucket(
                    ExternalBucketEvent(bucket_name=current.bucket_name, elapsed_ms=elapsed_ms)
                )
        finally:
            if should_record_callback:
                self.collector.record_tracer_callback_time((time.perf_counter() - callback_started) * 1000.0)
            self._callback_guard.active = False

    def _classify_frame(self, frame: types.FrameType, stack: list[_TraceFrame]) -> _TraceFrame | None:
        code = frame.f_code
        filename = code.co_filename
        if not filename:
            return None
        resolved_path = Path(filename).resolve()
        started_at = time.perf_counter()
        if self._is_excluded_resolved_path(resolved_path):
            return None
        relative_path = self._relative_project_path(resolved_path)
        if relative_path is not None and any(relative_path.startswith(prefix) for prefix in self._excluded_relative_prefixes):
            return None

        if self._is_project_file(resolved_path):
            if relative_path is None:
                return None
            function_name, symbol_key, display_name = self._symbol_identity(frame, relative_path, stack)
            if symbol_key is None or display_name is None or function_name is None:
                return None
            recursion_depth = 1 + sum(1 for item in stack if item.kind == "project" and item.symbol_key == symbol_key)
            return _TraceFrame(
                kind="project",
                started_at=started_at,
                file_path=relative_path,
                symbol_key=symbol_key,
                display_name=display_name,
                function_name=function_name,
                recursion_depth=recursion_depth,
            )

        bucket_name = self._external_bucket_name(frame, resolved_path)
        if bucket_name is None:
            return None
        track_external = not any(item.kind == "external" for item in reversed(stack))
        return _TraceFrame(
            kind="external",
            started_at=started_at,
            bucket_name=bucket_name,
            track_external=track_external,
        )

    def _is_project_file(self, resolved_path: Path) -> bool:
        if self._is_excluded_resolved_path(resolved_path):
            return False
        relative_path = self._relative_project_path(resolved_path)
        if relative_path is None:
            return False
        if any(relative_path.startswith(prefix) for prefix in self._excluded_relative_prefixes):
            return False
        return resolved_path.suffix == ".py"

    def _relative_project_path(self, resolved_path: Path) -> str | None:
        try:
            return resolved_path.relative_to(self.project_root).as_posix()
        except ValueError:
            return None

    def _is_excluded_resolved_path(self, resolved_path: Path) -> bool:
        try:
            resolved_path.relative_to(self._instrumentation_root)
            return True
        except ValueError:
            return False

    def _symbol_identity(
        self,
        frame: types.FrameType,
        relative_path: str,
        stack: list[_TraceFrame],
    ) -> tuple[str | None, str | None, str | None]:
        code = frame.f_code
        qualname = getattr(code, "co_qualname", code.co_name)
        if code.co_name == "<module>":
            return None, None, None
        if "<lambda>" in qualname or code.co_name == "<lambda>":
            for item in reversed(stack):
                if item.kind == "project" and item.file_path == relative_path and item.symbol_key and item.display_name and item.function_name:
                    return item.function_name, item.symbol_key, item.display_name
            return None, None, None

        normalized_qualname = qualname.replace(".<locals>.", ".")
        symbol_key = f"{relative_path}::{normalized_qualname}"
        display_name = f"{Path(relative_path).name}::{normalized_qualname}"
        return normalized_qualname, symbol_key, display_name

    def _external_bucket_name(self, frame: types.FrameType, resolved_path: Path) -> str | None:
        module_name = frame.f_globals.get("__name__", "")
        top_level_module = str(module_name).split(".", 1)[0] if module_name else ""
        stdlib_prefixes = {Path(sys.base_prefix).resolve()}
        if hasattr(sys, "stdlib_module_names") and top_level_module in sys.stdlib_module_names:
            return "external:stdlib"
        if any(str(resolved_path).startswith(str(prefix)) for prefix in stdlib_prefixes) and "site-packages" not in str(resolved_path):
            return "external:stdlib"
        if top_level_module:
            return f"external:{top_level_module}"
        return "external:unknown"
