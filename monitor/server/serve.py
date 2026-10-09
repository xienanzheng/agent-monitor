"""`monitor serve`: start the dashboard on 127.0.0.1 only, after checking it can start."""
import secrets
import socket
import threading
import webbrowser
from pathlib import Path

from monitor.server.settings import BUILD_HINT


def port_free(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def preflight(root, port: int) -> None:
    """Exit with the exact fix when the dashboard cannot start."""
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError:
        raise SystemExit("error: the dashboard extra is not installed: run `uv sync --extra dashboard`")
    if not (Path(root) / "dashboard" / "dist" / "index.html").is_file():
        raise SystemExit(f"error: the dashboard is not built: run `{BUILD_HINT}`")
    if not port_free(port):
        raise SystemExit(f"error: port {port} is already in use: try `uv run monitor serve --port {port + 1}`")


def build_settings(root, port: int, logs_dir, token: str, home=None) -> "ServerSettings":
    from monitor.config import load_config
    from monitor.server.settings import ServerSettings
    if home:
        socket_path = str(Path(home) / ".cache" / "agent-monitor" / "monitor.sock")
    else:
        socket_path = load_config().socket_path
    return ServerSettings(root=Path(root), logs_dir=Path(logs_dir), token=token, port=port,
                          home=Path(home) if home else Path.home(), socket_path=socket_path)


def serve(root, port: int, logs_dir, open_browser: bool = False, home=None) -> None:
    preflight(root, port)
    import uvicorn

    from monitor.server.app import create_app
    token = secrets.token_urlsafe(16)
    try:
        settings = build_settings(root, port, logs_dir, token, home=home)
    except ValueError as e:
        raise SystemExit(f"error: {e}")
    url = f"http://127.0.0.1:{port}/"
    print(f"dashboard: {url}  (Ctrl-C to stop)")
    print(f"run token (already in the page; only needed for scripted POSTs): {token}")
    if open_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    uvicorn.run(create_app(settings), host="127.0.0.1", port=port, log_level="warning")
