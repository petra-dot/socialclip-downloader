import argparse
import json
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
        convert=output_type == "MP4", target_resolution=args.resolution,
        cookies_file=args.cookies,
    )
    return _emit(result, args.json)


def _cmd_convert(args) -> int:
    if _ffmpeg_missing():
        return _dep_error(
            args, "ffmpeg",
            "ffmpeg not found. Install ffmpeg and ensure it is on PATH.",
        )
    from core.convert import convert_file
    output_type = {"mp4": "MP4", "mp3": "MP3", "wav": "WAV"}[args.to]
    result = convert_file(args.file, output_type,
                          args.resolution if output_type == "MP4" else None)
    return _emit(result, args.json)


def _cmd_doctor(args) -> int:
    from utils.ffmpeg import find_ffmpeg
    found = find_ffmpeg()
    data = {"ffmpeg": found or None, "ffmpeg_found": bool(found)}
    if args.json:
        print(json.dumps(data))
    else:
        print(f"ffmpeg: {found or 'NOT FOUND'}")
    return EXIT_OK if found else EXIT_DEP


def _cmd_manifest_schema(args) -> int:
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "socialclip result",
        "type": "object",
        "properties": {
            "schema_version": {"const": SCHEMA_VERSION},
            "status": {"enum": ["ok", "error"]},
            "error_category": {
                "enum": [None, "blocked", "format", "ffmpeg", "network",
                         "not_found", "other"]
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
    d.add_argument("--resolution", type=int, default=1080)
    d.add_argument("--cookies")
    d.set_defaults(func=_cmd_download)

    c = sub.add_parser("convert")
    c.add_argument("file")
    c.add_argument("--json", action="store_true")
    c.add_argument("--to", choices=["mp4", "mp3", "wav"], default="mp3")
    c.add_argument("--resolution", type=int, default=1080)
    c.set_defaults(func=_cmd_convert)

    doc = sub.add_parser("doctor")
    doc.add_argument("--json", action="store_true")
    doc.set_defaults(func=_cmd_doctor)

    ms = sub.add_parser("manifest-schema")
    ms.set_defaults(func=_cmd_manifest_schema)

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
