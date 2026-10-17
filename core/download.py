import os
import subprocess

from core.clip import ClipSpec, clip_ffmpeg_args
from core.formats import EDITOR_SAFE_A
from core.manifest import error_result, result_from_info
from core.pipeline import plan_postprocess
from core.probe import probe_media
from core.progress import Progress
from sites.errors import classify_error
from utils.ffmpeg import ffmpeg_path
from utils.file_utils import (
    clean_title,
    get_uploader,
    is_generic_title,
    make_unique_filepath,
)
from utils.ydl_opts import (
    _ffmpeg_to_nle_mp4,
    _nle_ydl_opts,
    ffprobe_get_height,
    strip_ansi,
)


def needs_universal_reencode(src_info: dict) -> bool:
    """True when a saved MP4 is not H.264 video + editor-safe audio.

    WhatsApp and Facebook reject VP9/AV1/HEVC videos and editors reject
    Opus/Vorbis audio inside MP4. Sites such as Instagram serve those, so
    after downloading we re-encode to guarantee the file is universally
    playable. An unconfirmed codec re-encodes too: a needless re-encode is
    better than a file that uploads nowhere.
    """
    info = src_info or {}
    vcodec = (info.get("vcodec") or "").lower()
    acodec = (info.get("acodec") or "").lower()
    if vcodec != "h264":
        return True
    # An absent audio codec is fine (silent video); a present hostile one is not.
    if acodec and acodec not in EDITOR_SAFE_A:
        return True
    return False


class DownloadCancelled(Exception):
    """Raised from the progress hook when the caller requests cancellation."""


def _title_without_cookies(url, cookies_file, cookies_from_browser):
    """The video's title when fetched without cookies, or "".

    Facebook hands back a generic title when cookies are sent, but the real one
    when they are not. Returns "" on any failure - the caller falls back.
    """
    try:
        from yt_dlp import YoutubeDL
    except Exception:
        return ""
    opts = {"skip_download": True, "noplaylist": True, "quiet": True,
            "no_warnings": True, "noprogress": True, "no_color": True}
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        return ""
    if not isinstance(info, dict):
        return ""
    return info.get("title") or ""


def better_base_name(info, url=None, cookies_file=None,
                     cookies_from_browser=None, title_lookup=None):
    """A usable file base name for `info`, never the site's own name.

    Order: the real title (re-fetched without cookies when the site gave a
    generic one) -> uploader plus the video id -> the id -> whatever is left.
    `title_lookup(url, cookies_file, cookies_from_browser) -> str` is
    injectable for tests.
    """
    title = (info or {}).get("title")
    if not is_generic_title(title, info):
        return clean_title(title)

    if url is not None:
        lookup = title_lookup or _title_without_cookies
        try:
            alt = lookup(url, cookies_file, cookies_from_browser)
        except Exception:
            alt = ""
        if alt and not is_generic_title(alt, info):
            return clean_title(alt)

    # clean_title("") is "video", so an absent uploader must not take that value
    # or the uploader/id branch would fire with a bogus "video" prefix.
    raw_uploader = get_uploader(info) or ""
    uploader = clean_title(raw_uploader) if raw_uploader else ""
    vid = ((info or {}).get("id") or "").strip()
    if uploader and vid:
        return clean_title("%s_%s" % (uploader, vid))
    if vid or uploader:
        return clean_title(vid or uploader)
    # Nothing usable at all: "video" beats naming the file after the site.
    return "video"


def _discard(path):
    """Remove a failed ffmpeg output so it is never mistaken for a good file."""
    try:
        if path and os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


def _cleanup_partial(created_paths):
    """Remove only the files this run wrote.

    ``created_paths`` is the set of in-flight paths the yt-dlp progress hook
    reported. For each, remove the artifact and its exact temp sibling
    (``path + ".part"``). Never glob a shared base: a same-base ``.part`` left
    by an earlier run or another program is not ours to delete.
    """
    for path in created_paths:
        if not path:
            continue
        for candidate in (path, path + ".part"):
            try:
                if os.path.isfile(candidate):
                    os.remove(candidate)
            except OSError:
                pass


def _clip_name(path, clip):
    """<base>_clip_<start>-<end><ext> with whole seconds."""
    base, ext = os.path.splitext(path)
    start = int(round(clip.start))
    end = "end" if clip.end is None else str(int(round(clip.end)))
    return "%s_clip_%s-%s%s" % (base, start, end, ext)


def _cut_file(path, clip):
    """Cut `path` to `clip`. Returns the new path, or None on failure."""
    out = _clip_name(path, clip)
    cmd = [ffmpeg_path(), "-i", path] + clip_ffmpeg_args(clip) + ["-y", out]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        _discard(out)
        return None
    return out


def _section_range(clip):
    rng = {"start_time": clip.start}
    if clip.end is not None:
        rng["end_time"] = clip.end
    return lambda info, ydl: [rng]


def download_one(url, outtmpl, output_type, convert, target_resolution,
                 cookies_file=None, progress=None, cancel=None,
                 subtitles="off", embed_thumbnail=False, format_id=None,
                 clip=None, archive=None, cookies_from_browser=None):
    in_flight = {"created": set()}
    saw_download = {"value": False}
    try:
        from sites.cookies import resolve_cookie_file
        # An explicit path is an override; otherwise find this URL's platform
        # cookie file. This is what makes the Queue and an empty field work.
        cookies_file = resolve_cookie_file(url, cookies_file)

        from yt_dlp import YoutubeDL

        def hook(d):
            # yt-dlp reports the target in `filename` and the temp file it is
            # actually writing in `tmpfilename` (normally `<filename>.part`).
            if d.get("filename"):
                in_flight["created"].add(d["filename"])
            if d.get("tmpfilename"):
                in_flight["created"].add(d["tmpfilename"])
            if d.get("status") in ("downloading", "finished"):
                saw_download["value"] = True
            if cancel and cancel():
                raise DownloadCancelled()
            if progress:
                if d.get("status") == "downloading":
                    total = d.get("total_bytes") or d.get("total_bytes_estimate")
                    downloaded = int(d.get("downloaded_bytes", 0) or 0)
                    pct = int(downloaded / total * 100) if total else 0
                    progress(Progress(
                        percent=pct,
                        speed=d.get("speed"),
                        eta=d.get("eta"),
                        downloaded=downloaded,
                        total=total,
                    ))
                elif d.get("status") == "finished":
                    progress(Progress(percent=100, speed=None, eta=None,
                                      downloaded=0, total=None))

        hooks = [hook]

        ydl_opts = _nle_ydl_opts(
            outtmpl=outtmpl, progress_hooks=hooks, cookies_file=cookies_file,
            archive_file=archive if clip is None else None,
            cookies_from_browser=cookies_from_browser,
        )
        section_ok = False
        if clip is not None:
            ydl_opts["download_ranges"] = _section_range(clip)
            if clip.exact:
                ydl_opts["force_keyframes_at_cuts"] = True
        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                downloaded_file = ydl.prepare_filename(info) if info else None
            section_ok = clip is not None
        except DownloadCancelled:
            raise
        except Exception:
            if clip is None:
                raise
            full_opts = _nle_ydl_opts(
                outtmpl=outtmpl, progress_hooks=hooks, cookies_file=cookies_file,
                archive_file=archive if clip is None else None,
                cookies_from_browser=cookies_from_browser,
            )
            with YoutubeDL(full_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                downloaded_file = ydl.prepare_filename(info) if info else None

        if not info:
            # With the archive on, an already-recorded video can come back as no
            # info at all. Report it as skipped rather than an error: a genuine
            # extraction failure raises above, so this branch only sees the
            # archive's own no-op.
            if archive and clip is None:
                return error_result(
                    "skipped", "Already downloaded; skipped.", url
                )
            return error_result(
                "not_found",
                "Could not extract video info. The video may be private, "
                "deleted, or region-locked.",
                url,
            )

        if archive and clip is None and not saw_download["value"]:
            return error_result(
                "skipped", "Already downloaded; skipped.", url
            )

        # A site can hand back a title that is just its own name (Facebook does
        # this when cookies are sent), which would name the file after the site.
        if downloaded_file and os.path.isfile(downloaded_file):
            current_base = os.path.splitext(os.path.basename(downloaded_file))[0]
            if is_generic_title(current_base, info):
                better = better_base_name(
                    info, url=url, cookies_file=cookies_file,
                    cookies_from_browser=cookies_from_browser,
                )
                if better and better != current_base:
                    _, current_ext = os.path.splitext(downloaded_file)
                    target = make_unique_filepath(
                        os.path.dirname(downloaded_file), better,
                        current_ext.lstrip("."), fallback_id=info.get("id"),
                    )
                    try:
                        os.replace(downloaded_file, target)
                        downloaded_file = target
                    except OSError:
                        pass

        if clip is not None and os.path.isfile(downloaded_file):
            moved = False
            if section_ok:
                # yt-dlp already cut the section; just give it our name.
                renamed = _clip_name(downloaded_file, clip)
                try:
                    os.replace(downloaded_file, renamed)
                    downloaded_file = renamed
                    moved = True
                except OSError:
                    moved = False
            if not moved:
                cut = _cut_file(downloaded_file, clip)
                if cut:
                    os.remove(downloaded_file)
                    downloaded_file = cut
                else:
                    return error_result(
                        "ffmpeg",
                        "The clip could not be cut. The full video was kept at "
                        "%s." % downloaded_file,
                        url,
                    )

        if not os.path.exists(downloaded_file):
            base = os.path.splitext(downloaded_file)[0]
            if os.path.exists(base + ".mp4"):
                downloaded_file = base + ".mp4"

        final_height = info.get("height") or ffprobe_get_height(downloaded_file)
        action = plan_postprocess(output_type, convert, final_height, target_resolution)
        final_path = downloaded_file

        if action == "audio":
            mp3_path = os.path.splitext(downloaded_file)[0] + ".mp3"
            cmd = [ffmpeg_path(), "-i", downloaded_file, "-q:a", "0", "-map", "a",
                   "-y", mp3_path]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode != 0:
                _discard(mp3_path)
                return error_result(
                    "ffmpeg",
                    result.stderr.decode(errors="ignore"),
                    url,
                )
            os.remove(downloaded_file)
            final_path = mp3_path
        elif action == "convert":
            base, _ = os.path.splitext(downloaded_file)
            out_file = f"{base}_{target_resolution}p.mp4"
            result = _ffmpeg_to_nle_mp4(downloaded_file, out_file, target_resolution)
            if result.returncode != 0:
                _discard(out_file)
                return error_result("ffmpeg", result.stderr.decode(errors="ignore"), url)
            os.remove(downloaded_file)
            final_path = out_file

        # Universal-playability guarantee: some sites (Instagram) serve only
        # VP9/AV1. A plain MP4 download can therefore contain a codec that
        # WhatsApp and Facebook reject, so re-encode an H.264-less MP4. This
        # runs for every retained MP4, including skip_low/skip_equal: a
        # resolution decision must not skip the codec guarantee. The convert
        # and audio actions already emit H.264/AAC or MP3.
        reencoded = False
        if (output_type == "MP4" and action in ("keep", "skip_low", "skip_equal")
                and os.path.isfile(final_path)):
            src_info = probe_media(final_path)
            if needs_universal_reencode(src_info):
                base, _ = os.path.splitext(final_path)
                out_file = f"{base}_h264.mp4"
                result = _ffmpeg_to_nle_mp4(final_path, out_file, None)
                if result.returncode != 0:
                    _discard(out_file)
                    return error_result(
                        "ffmpeg", result.stderr.decode(errors="ignore"), url
                    )
                os.remove(final_path)
                final_path = out_file
                reencoded = True

        if (subtitles and subtitles != "off" and action != "audio"
                and clip is None and os.path.isfile(final_path)):
            from core.subtitles import (
                embed_subtitles, subtitle_tracks, write_subtitle,
            )

            base = os.path.splitext(final_path)[0]
            sidecars = []
            for track in subtitle_tracks(info):
                if cancel and cancel():
                    raise DownloadCancelled()
                written = write_subtitle(track, base)
                if written:
                    in_flight["created"].add(written)
                    sidecars.append((track.lang, written))
            embedded = False
            if subtitles in ("embed", "both") and sidecars:
                embedded = embed_subtitles(final_path, sidecars)
            if subtitles == "embed" and embedded:
                for _lang, path in sidecars:
                    try:
                        os.remove(path)
                    except OSError:
                        pass

        if reencoded:
            message = f"Re-encoded for editor compatibility: {final_path}"
        elif action == "skip_low":
            message = (f"Skipped conversion: source ({final_height}p) is lower than "
                       f"target ({target_resolution}p). No upscaling.")
        elif action == "skip_equal":
            message = (f"Skipped conversion: source resolution equals target "
                       f"({final_height}p).")
        elif action == "audio":
            message = f"MP3 saved: {final_path}"
        elif action == "convert":
            message = f"Conversion completed: {final_path}"
        else:
            message = f"Download finished: {final_path}"

        manifest = result_from_info(info, final_path, url)
        manifest.message = message
        # Extension must describe the artifact we actually hand back, not the
        # container yt-dlp extracted (e.g. MP3 output keeps info["ext"] == "mp4").
        manifest.extension = os.path.splitext(final_path)[1].lstrip(".")
        manifest.height = final_height or manifest.height
        manifest.bytes = os.path.getsize(final_path) if os.path.isfile(final_path) else 0
        return manifest

    except DownloadCancelled:
        _cleanup_partial(in_flight["created"])
        return error_result("cancelled", "Cancelled.", url)
    except Exception as e:
        _cleanup_partial(in_flight["created"])
        category, message = classify_error(strip_ansi(str(e)), url)
        return error_result(category, message, url)
