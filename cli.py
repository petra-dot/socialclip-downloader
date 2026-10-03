import argparse
import json
import os
import shutil
import sys

from core.manifest import SCHEMA_VERSION

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2
EXIT_DEP = 3


def _emit(result, as_json: bool) -> int:
    data = result.to_dict()
    if as_json:
        # Contract: exactly one JSON object on stdout, human text on stderr only.
        print(json.dumps(data))
    else:
        if data["status"] == "ok":
            print(data["path"] or data["message"] or "ok")
        else:
            print(f"error: {data['message']}", file=sys.stderr)
    return EXIT_OK if data["status"] == "ok" else EXIT_FAIL


def _ytdlp_missing() -> bool:
    import importlib.util
    return importlib.util.find_spec("yt_dlp") is None


def _ffmpeg_missing() -> bool:
    from utils.ffmpeg import ffmpeg_path
    return ffmpeg_path() == "ffmpeg" and not _on_path("ffmpeg")


def _dep_error(args, category: str, message: str, url: str = "") -> int:
    from core.manifest import error_result
    _emit(error_result(category, message, url), args.json)
    return EXIT_DEP


def _cmd_download(args) -> int:
    if _ytdlp_missing():
        return _dep_error(
            args, "other", "yt-dlp not found. Install it with: pip install yt-dlp",
            args.url,
        )
    if _ffmpeg_missing():
        return _dep_error(
            args, "ffmpeg",
            "ffmpeg not found. Install ffmpeg and ensure it is on PATH.",
            args.url,
        )
    from core.download import download_one
    from utils.file_utils import default_download_folder
    out_dir = args.output or default_download_folder()
    outtmpl = f"{out_dir}/%(title)s.%(ext)s"
    output_type = "MP3" if args.format == "mp3" else "MP4"
    result = download_one(
        args.url, outtmpl=outtmpl, output_type=output_type,
        convert=args.convert, target_resolution=args.resolution,
        cookies_file=args.cookies,
    )
    return _emit(result, args.json)


def _cmd_convert(args) -> int:
    from core import formats

    if args.copy_streams is not None and args.to is None:
        print("--copy/--no-copy require --to", file=sys.stderr)
        return EXIT_USAGE

    target_format = None
    if args.to is not None:
        if formats.get(args.to) is None:
            print(
                f"error: unknown format '{args.to}'. "
                f"Valid formats: {', '.join(formats.keys())}",
                file=sys.stderr,
            )
            return EXIT_USAGE
        target_format = args.to

    if _ffmpeg_missing():
        return _dep_error(
            args, "ffmpeg",
            "ffmpeg not found. Install ffmpeg and ensure it is on PATH.",
        )
    from core.convert import convert_file

    if target_format is not None:
        result = convert_file(args.file, target_format=target_format,
                              copy_streams=args.copy_streams,
                              target_resolution=args.resolution)
    else:
        result = convert_file(args.file, "MP3")
    return _emit(result, args.json)


def _cmd_doctor(args) -> int:
    from core.doctor import run_checks
    report = run_checks()
    if args.json:
        print(json.dumps(report))
    else:
        ff = report["ffmpeg"]
        print(f"ffmpeg: {ff['path'] or 'NOT FOUND'}")
        if ff.get("version"):
            print(f"  {ff['version']}")
        found = [c for c in report["cookies"] if c["found"]]
        print(f"cookies: {len(found)} of {len(report['cookies'])} platforms")
        for c in found:
            print(f"  {c['platform']}: {c['path']}")
        net = report["network"]
        print(f"network: {net['detail']}")
    return EXIT_OK if report["ffmpeg"]["found"] else EXIT_DEP


def _queue_path() -> str:
    from sites.cookies import default_cookie_dir
    override = os.environ.get("SOCIALCLIP_QUEUE")
    if override:
        return override
    return os.path.join(default_cookie_dir(), "queue.json")


def _load_queue():
    from core.queue import Queue, QueueStore
    store = QueueStore(_queue_path())
    store.load()
    return Queue(store)


def _job_dict(job) -> dict:
    return {"id": job.id, "url": job.url, "state": job.state,
            "message": job.message, "path": job.path}


def _queue_executor(job):
    from core.download import download_one
    from core.queue import resolve_outtmpl
    opts = job.options or {}
    outtmpl = resolve_outtmpl(opts)
    return download_one(
        job.url,
        outtmpl=outtmpl,
        output_type=opts.get("output_type", "MP4"),
        convert=opts.get("convert", False),
        target_resolution=opts.get("target_resolution", 1080),
        cookies_file=opts.get("cookies_file"),
    )


def _cmd_queue(args) -> int:
    command = args.queue_command
    queue = _load_queue()

    if command == "add":
        queue.add_many(args.urls)
        queue.store.save()
        n = len(args.urls)
        if args.json:
            print(json.dumps({"schema_version": SCHEMA_VERSION, "added": n}))
        else:
            print(f"added {n}")
        return EXIT_OK

    if command == "list":
        jobs = [_job_dict(j) for j in queue.jobs]
        if args.json:
            print(json.dumps({"schema_version": SCHEMA_VERSION, "jobs": jobs}))
        else:
            for j in jobs:
                print(f"{j['state']}\t{j['url']}")
        return EXIT_OK

    if command == "clear":
        n = len(queue.jobs)
        queue.jobs.clear()
        queue.store.save()
        if args.json:
            print(json.dumps({"schema_version": SCHEMA_VERSION, "cleared": n}))
        else:
            print(f"cleared {n}")
        return EXIT_OK

    if command == "run":
        if _ytdlp_missing():
            return _dep_error(
                args, "other", "yt-dlp not found. Install it with: pip install yt-dlp",
            )
        if _ffmpeg_missing():
            return _dep_error(
                args, "ffmpeg",
                "ffmpeg not found. Install ffmpeg and ensure it is on PATH.",
            )
        run = done = failed = cancelled = 0
        while True:
            job = queue.run_once(_queue_executor)
            if job is None:
                break
            queue.store.save()
            run += 1
            if job.state == "done":
                done += 1
            elif job.state == "failed":
                failed += 1
            elif job.state == "cancelled":
                cancelled += 1
        result = {"schema_version": SCHEMA_VERSION, "run": run, "done": done,
                  "failed": failed, "cancelled": cancelled}
        if args.json:
            print(json.dumps(result))
        else:
            print(f"run {run}: {done} done, {failed} failed, {cancelled} cancelled")
        return EXIT_OK


def _cmd_manifest_schema(args) -> int:
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "socialclip result",
        "type": "object",
        "properties": {
            "schema_version": {"const": SCHEMA_VERSION},
            "status": {"enum": ["ok", "error"]},
            "error_category": {
                "enum": [None, "blocked", "cancelled", "format", "ffmpeg",
                         "network", "not_found", "other"]
            },
        },
        "required": ["schema_version", "status"],
    }
    print(json.dumps(schema))
    return EXIT_OK


def _on_path(name: str) -> bool:
    return shutil.which(name) is not None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="socialclip")
    sub = parser.add_subparsers(dest="command", required=True)

    d = sub.add_parser("download")
    d.add_argument("url")
    d.add_argument("--json", action="store_true")
    d.add_argument("--output")
    d.add_argument("--format", choices=["mp4", "mp3"], default="mp4")
    d.add_argument("--convert", action="store_true",
                   help="re-encode down to --resolution (default: keep original)")
    d.add_argument("--resolution", type=int, default=1080,
                   help="target height, only used with --convert")
    d.add_argument("--cookies")
    d.set_defaults(func=_cmd_download)

    c = sub.add_parser("convert")
    c.add_argument("file")
    c.add_argument("--json", action="store_true")
    c.add_argument("--to",
                   help="target format key from the registry (e.g. mp4, mkv, webm, "
                        "mp3, wav, aac); defaults to the legacy MP3 path")
    c.add_argument("--resolution", type=int, default=1080,
                   help="target height for video format targets; ignored for audio")
    c.add_argument("--copy", dest="copy_streams", action="store_true",
                   default=None,
                   help="stream-copy without re-encoding (requires --to)")
    c.add_argument("--no-copy", dest="copy_streams", action="store_false",
                   default=None,
                   help="force re-encode (requires --to)")
    c.set_defaults(func=_cmd_convert)

    doc = sub.add_parser("doctor")
    doc.add_argument("--json", action="store_true")
    doc.set_defaults(func=_cmd_doctor)

    ms = sub.add_parser("manifest-schema")
    ms.set_defaults(func=_cmd_manifest_schema)

    q = sub.add_parser("queue")
    qsub = q.add_subparsers(dest="queue_command", required=True)

    qa = qsub.add_parser("add")
    qa.add_argument("urls", nargs="+")
    qa.add_argument("--json", action="store_true")
    qa.set_defaults(func=_cmd_queue)

    ql = qsub.add_parser("list")
    ql.add_argument("--json", action="store_true")
    ql.set_defaults(func=_cmd_queue)

    qr = qsub.add_parser("run")
    qr.add_argument("--json", action="store_true")
    qr.set_defaults(func=_cmd_queue)

    qc = qsub.add_parser("clear")
    qc.add_argument("--json", action="store_true")
    qc.set_defaults(func=_cmd_queue)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        # argparse prints usage to stderr and exits 2; map to the CLI contract.
        return EXIT_USAGE if e.code else EXIT_OK
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
