from __future__ import annotations

import socket
import threading
import time
from contextlib import suppress
from dataclasses import dataclass

import uvicorn
from fastapi import FastAPI

from backend.app.main import create_app


@dataclass
class ServerHandle:
    url: str
    server: uvicorn.Server
    thread: threading.Thread
    socket: socket.socket

    def stop(self, timeout: float = 8.0) -> None:
        self.server.should_exit = True
        self.thread.join(timeout)
        if self.thread.is_alive():
            self.server.force_exit = True
            self.thread.join(2.0)
        with suppress(OSError):
            self.socket.close()


def start_server(app: FastAPI | None = None, *, timeout: float = 10.0) -> ServerHandle:
    application = app or create_app()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = int(sock.getsockname()[1])
    config = uvicorn.Config(
        application,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
        # PyInstaller windowed executables set sys.stdout/sys.stderr to None.
        # Disable Uvicorn's default logging config because its formatter calls isatty().
        log_config=None,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [sock]},
        name="FireLens-Uvicorn",
        daemon=True,
    )
    thread.start()
    deadline = time.monotonic() + timeout
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.02)
    if not server.started:
        server.should_exit = True
        thread.join(2.0)
        sock.close()
        raise RuntimeError("FireLens 內部服務啟動失敗")
    return ServerHandle(url=f"http://127.0.0.1:{port}", server=server, thread=thread, socket=sock)
