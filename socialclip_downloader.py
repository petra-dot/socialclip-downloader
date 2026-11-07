import os
import sys

from core.version import __version__  # noqa: F401 - re-exported

try:
    from PyQt5 import QtWidgets, QtCore, QtGui
except Exception:
    QtWidgets = None
    QtCore = None
    QtGui = None


def _asset_path(name: str) -> str:
    """Resolve a bundled asset for both a source run and a PyInstaller build."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        candidate = os.path.join(base, "assets", name)
        if os.path.isfile(candidate):
            return candidate
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "assets", name)


def _host_options(msg: dict) -> dict:
    """The option dict a browser-started job runs with."""
    from core.queue import build_job_options
    from utils.file_utils import default_download_folder

    output = msg.get("output") if msg.get("output") in ("MP4", "MP3") else "MP4"
    resolution = str(msg.get("resolution") or "1080")
    if not resolution.isdigit():
        resolution = "1080"
    save_dir = default_download_folder()
    cookies = ""
    browser = ""
    try:
        from PyQt5.QtCore import QSettings

        settings = QSettings("petra-dot", "SocialClip Downloader")
        save_dir = settings.value("batch/save_dir") or save_dir
        cookies = settings.value("batch/cookies") or ""
        browser = settings.value("cookies/browser") or ""
    except Exception:
        pass
    return build_job_options(save_dir, output, resolution, cookies, "off", browser)


def _launch_gui(start: bool) -> None:
    """Start the app detached, without handing it the browser's pipes."""
    import subprocess

    if getattr(sys, "frozen", False):
        args = [sys.executable]
    else:
        args = [sys.executable, os.path.abspath(__file__)]
    if start:
        args.append("--run-queue")
    try:
        subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except OSError:
        pass


def _hand_off(msg: dict, options: dict) -> bool:
    """Give a running window the job, so it appears without a restart.

    The host has no window of its own; when one is up it owns the queue and
    should do the write, which also starts the job when asked.
    """
    try:
        from PyQt5.QtCore import QCoreApplication

        from ui.ipc import send_to_primary
    except Exception:
        return False
    if QCoreApplication.instance() is None:
        QCoreApplication([])
    urls = [u for u in msg.get("urls") or [] if isinstance(u, str) and u.strip()]
    payload = {
        "action": "add",
        "urls": urls,
        "options": options,
        "start": bool(msg.get("start")),
    }
    try:
        return send_to_primary(payload)
    except Exception:
        return False


def run_native_host() -> int:
    """Answer one native message and exit. Nothing else may touch stdout."""
    from core.history import HistoryStore
    from core.native import ProtocolError, encode_message, handle_message, read_message
    from core.native_io import stdin_stream, stdout_stream
    from core.paths import migrate_legacy_files, queue_path
    from core.queue import QueueFileError, QueueStore

    migrate_legacy_files()
    msg = {}
    handed_off = False
    try:
        msg = read_message(stdin_stream())
        cmd = msg.get("cmd")
        options = _host_options(msg) if cmd == "add" else {}
        store = QueueStore(queue_path())
        if cmd in ("add", "check"):
            store.load_strict()
        if cmd == "add" and _hand_off(msg, options):
            handed_off = True
            reply = {"ok": True, "added": len(msg.get("urls") or [])}
        else:
            reply = handle_message(msg, store, HistoryStore(), options)
    except ProtocolError as exc:
        reply = {"ok": False, "error": "bad message: %s" % exc}
    except QueueFileError as exc:
        reply = {"ok": False, "error": "queue unreadable: %s" % exc}
    except Exception as exc:  # the browser only sees what we reply
        reply = {"ok": False, "error": "%s" % exc}

    out = stdout_stream()
    out.write(encode_message(reply))
    out.flush()
    if reply.get("ok") and msg.get("start") and not handed_off:
        _launch_gui(start=True)
    return 0


def install_native_host(argv) -> int:
    """Write the host manifests and register them for each browser."""
    from core.native_install import FIREFOX_ADDON_ID, install
    from core.paths import migrate_legacy_files

    migrate_legacy_files()
    extension_id = ""
    if "--extension-id" in argv:
        position = argv.index("--extension-id")
        if position + 1 < len(argv):
            extension_id = argv[position + 1]
    if not extension_id:
        print("usage: --install-native-host --extension-id <chromium extension id>")
        return 2
    frozen = bool(getattr(sys, "frozen", False))
    target = sys.executable if frozen else os.path.abspath(__file__)
    written = install(target, extension_id, frozen=frozen)
    print("Firefox add-on id: %s" % FIREFOX_ADDON_ID)
    for path in written:
        print("registered %s" % path)
    return 0


def main():
    if "--native-host" in sys.argv:
        return run_native_host()

    if "--install-native-host" in sys.argv:
        return install_native_host(sys.argv)

    from core.paths import migrate_legacy_files
    from utils.ytdlp import load
    migrate_legacy_files()
    load()

    if "--apply-update" in sys.argv:
        from core.updater import apply_update

        argv = sys.argv
        target = None
        if "--target" in argv:
            try:
                target = argv[argv.index("--target") + 1]
            except IndexError:
                target = None
        if not target:
            print("usage: --apply-update --target PATH")
            return 2
        return apply_update(target)

    missing = []
    try:
        import yt_dlp  # noqa: F401 - presence check; load() already ran
    except Exception:
        missing.append(
            "yt-dlp (Python package 'yt-dlp') - install with: pip install yt-dlp"
        )
    if QtWidgets is None or QtCore is None:
        missing.append("PyQt5 - install with: pip install PyQt5")
    if missing:
        print("Missing required dependencies:")
        for m in missing:
            print(" - ", m)
        print("Or install all via: pip install -r requirements.txt")
        sys.exit(1)

    from ui.main_window import MainWindow

    # Must be set before QApplication is constructed, otherwise it is a no-op.
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps)

    app = QtWidgets.QApplication(sys.argv)
    app.setOrganizationName("petra-dot")
    app.setApplicationName("SocialClip Downloader")

    from ui.ipc import IpcServer, reset_server, send_to_primary

    run_queue = "--run-queue" in sys.argv
    if send_to_primary({"action": "run" if run_queue else "show"}):
        return 0

    icon_path = _asset_path("icon.ico")
    if os.path.isfile(icon_path):
        app.setWindowIcon(QtGui.QIcon(icon_path))

    from utils.ffmpeg import find_ffmpeg
    if not find_ffmpeg():
        # print() is invisible in the --windowed build (no stdout), so warn in the GUI.
        QtWidgets.QMessageBox.warning(
            None,
            "ffmpeg not found",
            "ffmpeg was not found on PATH or in common install locations.\n\n"
            "Downloads that need merging or conversion will fail.\n\n"
            "Install it with:\n"
            "  Windows: winget install Gyan.FFmpeg\n"
            "  macOS:   brew install ffmpeg\n"
            "  Linux:   sudo apt install ffmpeg",
        )

    window = MainWindow()
    server = IpcServer(window)
    if not server.listen():
        # A crashed run can leave the name behind on POSIX; nothing answered
        # above, so taking it back is safe.
        reset_server()
        server.listen()
    server.json_received.connect(window.on_ipc_message)
    window.ipc_server = server
    window.show()
    # Paint the first frame before the startup checks run: they import yt-dlp
    # and spawn ffmpeg, and doing that with the window already mapped shows a
    # blank frame first.
    QtWidgets.QApplication.processEvents()
    window.start_background_work()
    if run_queue:
        window.tabs.setCurrentWidget(window.batch_tab)
        window.batch_tab.start_queue(confirm=False)
    sys.exit(app.exec_())


if __name__ == "__main__":
    sys.exit(main())
