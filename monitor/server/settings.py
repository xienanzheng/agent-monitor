"""Server settings, injectable for tests (root, logs dir, home, socket path, built-page dir)."""
from dataclasses import dataclass, field
from pathlib import Path

SOURCES = ("live", "replay")
BUILD_HINT = "npm --prefix dashboard install && npm --prefix dashboard run build"


@dataclass(frozen=True)
class ServerSettings:
    root: Path
    logs_dir: Path
    token: str
    port: int = 8765
    home: Path = field(default_factory=Path.home)
    socket_path: str = "~/.cache/agent-monitor/monitor.sock"
    dist_dir: Path | None = None

    def dist(self) -> Path:
        return Path(self.dist_dir) if self.dist_dir is not None else Path(self.root) / "dashboard" / "dist"

    def source_dir(self, source: str) -> Path:
        if source == "live":
            return Path(self.logs_dir)
        if source == "replay":
            return Path(self.logs_dir) / "replay"
        raise ValueError(f"source must be one of {list(SOURCES)}, got {source!r}")
