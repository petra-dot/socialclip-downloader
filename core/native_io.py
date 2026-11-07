"""Binary stdin/stdout for the native host.

A windowed PyInstaller build gives the process ``None`` for ``sys.stdin`` and
``sys.stdout``, so the host opens the inherited OS handles instead. Sockets and
pipes can return short reads, which :func:`core.native.read_message` already
loops over.
"""

import os
import sys

STD_INPUT_HANDLE = -10
STD_OUTPUT_HANDLE = -11


def _raw_stream(handle_kind: int, writable: bool):
    import ctypes
    import msvcrt

    handle = ctypes.windll.kernel32.GetStdHandle(handle_kind)
    # O_RDONLY is 0 on Windows, so the writable case needs its own flag.
    # O_BINARY matters: text mode would rewrite \n and corrupt the framing.
    flags = (os.O_WRONLY if writable else os.O_RDONLY) | os.O_BINARY
    fd = msvcrt.open_osfhandle(handle, flags)
    return os.fdopen(fd, "wb" if writable else "rb", 0)


def stdin_stream():
    if sys.platform.startswith("win"):
        return _raw_stream(STD_INPUT_HANDLE, False)
    return sys.stdin.buffer


def stdout_stream():
    if sys.platform.startswith("win"):
        return _raw_stream(STD_OUTPUT_HANDLE, True)
    return sys.stdout.buffer
