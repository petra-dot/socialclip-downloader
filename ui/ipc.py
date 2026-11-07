"""Single-instance guard and the channel the native host reaches the app on.

A second launch (including one the browser started) hands its request to the
running window instead of becoming a second writer of ``queue.json``.
"""

import getpass
import json
import os

from PyQt5 import QtCore, QtNetwork


def server_name() -> str:
    """Named per user, and overridable so a test never touches a real window."""
    return os.environ.get("SOCIALCLIP_IPC") or ("socialclip-" + getpass.getuser())


def reset_server() -> None:
    """Drop a socket name a crashed instance left behind (POSIX only)."""
    QtNetwork.QLocalServer.removeServer(server_name())


def send_to_primary(payload: dict, timeout_ms: int = 400) -> bool:
    """True when a running instance took the message."""
    socket = QtNetwork.QLocalSocket()
    socket.connectToServer(server_name())
    if not socket.waitForConnected(timeout_ms):
        return False
    socket.write(json.dumps(payload).encode("utf-8"))
    socket.waitForBytesWritten(timeout_ms)
    socket.disconnectFromServer()
    return True


class IpcServer(QtCore.QObject):
    json_received = QtCore.pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._server = QtNetwork.QLocalServer(self)
        self._server.newConnection.connect(self._on_connection)

    def listen(self) -> bool:
        if self._server.isListening():
            return True
        return self._server.listen(server_name())

    def close(self) -> None:
        self._server.close()
        reset_server()

    def _on_connection(self) -> None:
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            socket.readyRead.connect(lambda s=socket: self._read(s))
            socket.disconnected.connect(socket.deleteLater)

    def _read(self, socket) -> None:
        raw = bytes(socket.readAll()).strip()
        if not raw:
            return
        try:
            payload = json.loads(raw.decode("utf-8"))
        except ValueError:
            return
        if isinstance(payload, dict):
            self.json_received.emit(payload)
