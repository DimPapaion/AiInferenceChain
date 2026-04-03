"""
Structured logging for InferenceChain.

Provides hierarchical logging with trace IDs for debugging distributed consensus.
All log entries include:
  - timestamp (ISO 8601)
  - level (DEBUG, INFO, WARN, ERROR)
  - component (e.g., "qoi_consensus", "node_0000...")
  - trace_id (optional, for correlating across messages)
  - message
  - context (optional extra fields)
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, Any
from enum import Enum


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


@dataclass
class LogEntry:
    """Structured log entry."""
    timestamp: str
    level: LogLevel
    component: str
    message: str
    trace_id: Optional[str] = None
    context: dict[str, Any] = None

    def __post_init__(self) -> None:
        if self.context is None:
            self.context = {}
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    def to_json(self) -> str:
        """Serialize to JSON."""
        d = asdict(self)
        d["level"] = self.level.value
        d["context"] = self.context or {}
        return json.dumps(d)

    def to_pretty(self) -> str:
        """Human-readable format."""
        trace = f" [trace:{self.trace_id}]" if self.trace_id else ""
        ctx = f" {json.dumps(self.context)}" if self.context else ""
        return (
            f"{self.timestamp} | {self.level.value:5s} | "
            f"{self.component:30s}{trace} | {self.message}{ctx}"
        )


class StructuredLogger:
    """
    Structured logger for consensus components.

    Usage:
        logger = StructuredLogger(component="qoi_consensus", node_id="abc...")
        logger.info("Consensus started", trace_id=request_id, context={"round": 1})
    """

    def __init__(
        self,
        component: str,
        output: str = "both",  # "json", "pretty", or "both"
    ) -> None:
        self.component = component
        self.output = output

    def _emit(self, entry: LogEntry) -> None:
        """Emit log entry to stdout."""
        if self.output in ("json", "both"):
            print(entry.to_json(), file=sys.stdout)
        if self.output in ("pretty", "both"):
            print(entry.to_pretty(), file=sys.stdout)

    def debug(
        self,
        message: str,
        trace_id: Optional[str] = None,
        context: Optional[dict] = None,
    ) -> None:
        """Log debug message."""
        entry = LogEntry(
            timestamp="",
            level=LogLevel.DEBUG,
            component=self.component,
            message=message,
            trace_id=trace_id,
            context=context or {},
        )
        self._emit(entry)

    def info(
        self,
        message: str,
        trace_id: Optional[str] = None,
        context: Optional[dict] = None,
    ) -> None:
        """Log info message."""
        entry = LogEntry(
            timestamp="",
            level=LogLevel.INFO,
            component=self.component,
            message=message,
            trace_id=trace_id,
            context=context or {},
        )
        self._emit(entry)

    def warn(
        self,
        message: str,
        trace_id: Optional[str] = None,
        context: Optional[dict] = None,
    ) -> None:
        """Log warning message."""
        entry = LogEntry(
            timestamp="",
            level=LogLevel.WARN,
            component=self.component,
            message=message,
            trace_id=trace_id,
            context=context or {},
        )
        self._emit(entry)

    def error(
        self,
        message: str,
        trace_id: Optional[str] = None,
        context: Optional[dict] = None,
    ) -> None:
        """Log error message."""
        entry = LogEntry(
            timestamp="",
            level=LogLevel.ERROR,
            component=self.component,
            message=message,
            trace_id=trace_id,
            context=context or {},
        )
        self._emit(entry)


# Global logger registry
_loggers: dict[str, StructuredLogger] = {}


def get_logger(component: str, output: str = "both") -> StructuredLogger:
    """Get or create a logger for a component."""
    if component not in _loggers:
        _loggers[component] = StructuredLogger(component, output=output)
    return _loggers[component]
