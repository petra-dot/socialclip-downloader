# yt-dlp media URL patterns

Which URLs on the seven supported platforms are a single downloadable item, and
whether a regex list can decide that.

Research date: 2026-11-08.
Primary source: the installed yt-dlp, version **2026.08.19** at
`C:\Users\User\AppData\Local\Programs\Python\Python314\Lib\site-packages\yt_dlp`.
Line numbers below refer to that install. All example URLs are synthetic
placeholders.

---

## Short answer

**Yes, an anchored regex whitelist is enough. Do not add a HEAD or probe call to
the scanner.**

Reason: yt-dlp's own URL classifier is a regex too. `InfoExtractor.suitable()`
is defined as `_VALID_URL` regex match and nothing else
(`extractor/common.py:628-632`), identical in the frozen-build
`lazy_extractors.py:57-72`. No network call happens before extraction. So a
runtime "ask yt-dlp" check is not a stricter version of the same decision, it is
the same decision, and a HEAD call is a different and weaker question ("does
this redirect somewhere reachable") that costs one request per link.

What yt-dlp's regexes cannot do is answer "single item versus page". Its
per-extractor regexes deliberately accept channel pages, feeds, profiles and
hashtags (`YoutubeTabIE`, `InstagramUserIE`, `TikTokUserIE`), and the fallback
`GenericIE._VALID_URL` is literally `r'.*'` (`extractor/generic.py:55`), so
"does any extractor match" is true for every URL. The whitelist has to be built
by hand from the *media* extractor classes, which is what the list at the end of
this document is.

Corollary: verification belongs at download time, where `sites/errors.py`
already classifies failures. The scanner's job is only "is this link shaped like
one item".

---

## Method

Read, in the installed tree:

| File | What was taken from it |
|---|---|
| `extractor/youtube/_video.py` | `YoutubeIE._VALID_URL`, and its `suitable()` override |
| `extractor/youtube/_tab.py` | `YoutubeTabIE`, `YoutubePlaylistIE` (the non-media shapes) |
| `extractor/youtube/_base.py` | `_RESERVED_NAMES`, `_PLAYLIST_ID_RE` |
| `extractor/youtube/_clip.py`, `_redirect.py`, `_search.py`, `_mistakes.py` | clip, `youtu.be?list=`, `embed/live_stream`, search, truncated id |
| `extractor/instagram.py` | `InstagramIE`, `InstagramUserIE`, `InstagramTagIE`, `InstagramStoryIE` |
| `extractor/tiktok.py` | `TikTokIE`, `TikTokUserIE`, `TikTokSoundIE`, `TikTokEffectIE`, `TikTokTagIE`, `TikTokCollectionIE`, `TikTokVMIE`, `TikTokLiveIE`, `DouyinIE` |
| `extractor/twitter.py` | `TwitterBaseIE._BASE_REGEX`, `TwitterIE`, `TwitterSpacesIE`, `TwitterShortenerIE` |
| `extractor/facebook.py` | `FacebookIE`, `FacebookReelIE` |
| `extractor/bilibili.py` | `BiliBiliIE`, bangumi, audio, space, list, live |
| `extractor/generic.py`, `common.py`, `lazy_extractors.py`, `YoutubeDL.py` | the classifier itself |

Two facts that shaped the whole answer:

1. **There is no `Douyin` file.** `DouyinIE` lives in `extractor/tiktok.py:1372`
   and accepts exactly one shape, `/video/<digits>`.
2. **`YoutubeDL` has no `suitable()` method** in this version (calling it raises
   `AttributeError`). `YoutubeDL.get_info_extractor()` takes an *ie_key*, not a
   URL (`YoutubeDL.py:916`). The only URL classifier is the classmethod
   `IE.suitable(url)`, which is the regex.

I verified the dispatch behaviour empirically: iterated
`gen_extractor_classes()` over a list of ~130 synthetic URLs and recorded the
first matching extractor. Results quoted below are from that run.

### The trap that decides YouTube

`YoutubeIE` overrides `suitable()`:

```python
# extractor/youtube/_video.py:1922-1929
@classmethod
def suitable(cls, url):
    from yt_dlp.utils import parse_qs
    qs = parse_qs(url)
    if qs.get('list', [None])[0]:
        return False
    return super().suitable(url)
```

So yt-dlp itself does **not** consider `watch?v=ID&list=PL...` a single video.
It routes that URL to `YoutubeTabIE`, i.e. a playlist. Measured:

| URL | `YoutubeIE.suitable()` | first matching extractor |
|---|---|---|
| `https://www.youtube.com/watch?v=aaaaaaaaaaa` | True | `youtube` |
| `https://www.youtube.com/watch?v=aaaaaaaaaaa&list=PLbbbbbbbbbb` | False | `youtube:tab` |
| `https://www.youtube.com/watch?v=aaaaaaaaaaa&t=10s` | True | `youtube` |
| `https://youtu.be/aaaaaaaaaaa?list=PLbbbbbbbbbb` | n/a | `YoutubeYtBe` (`_redirect.py:11`) |

The app sets `noplaylist: True` (`utils/ydl_opts.py:86`), so when the download
step gets such a URL it takes the video, not the list. That is why the
recommended whitelist still accepts `watch?v=` with `list=` present. See the
ambiguity table.

---

## Per platform

`file:line` is the yt-dlp evidence. "Single item" means an extractor exists that
returns one video or one audio track for that shape (a multi-item *page* such as
an Instagram carousel still counts as one item URL, see ambiguity table).

### YouTube

| Kind | Shape (synthetic example) | Evidence |
|---|---|---|
| single | `/watch?v=<11>` `https://www.youtube.com/watch?v=aaaaaaaaaaa` | `_video.py:86-120`, id at `:116` |
| single | `/shorts/<11>` | `_video.py:99` |
| single | `/live/<11>` (a live or a finished stream, same id space) | `_video.py:99` |
| single | `/embed/<11>`, `/v/<11>`, `/e/<11>` | `_video.py:99` |
| single | `youtu.be/<11>` (with or without `?si=`, `?t=`) | `_video.py:108` |
| single | `music.youtube.com/watch?v=<11>`, `m.youtube.com/watch?v=<11>` | `_video.py:89` allows any single-label subdomain |
| single | `/clip/<id>` | `_clip.py:8` |
| not | `youtube.com/` (recommended feed) | `_redirect.py:142` |
| not | `/@handle`, `/@handle/videos`, `/@handle/shorts`, `/@handle/playlists`, `/@handle/live` | `_tab.py:1071-1090` (`(?!reserved) direct urls`) |
| not | `/channel/UC...`, `/c/<name>`, `/user/<name>` | `_tab.py:1079` |
| not | `/feed/subscriptions`, `/feed/trending`, `/feed/you` | `_tab.py:1081` |
| not | `/hashtag/<tag>` | `_tab.py:1081` |
| not | `/playlist?list=PL...` | `_tab.py:1082`, `_tab.py:2447` |
| not | `/watch?list=PL...` (no `v=`) | `_tab.py:1082` |
| not | `/shorts` (the feed, not a video) | no `{11}` id, `_video.py:99` |
| not | `/results?search_query=...` | `_search.py:34` |
| not | `/premium`, `/about/`, `/t/terms`, `/account`, `/upload`, `/create` | listed as reserved, `_base.py:456-460`; `/premium` and `/create` still land on `youtube:tab`, which is a page, not an item |
| not | `studio.youtube.com/...` | `_tab.py:1072` allows any subdomain, so studio is treated as a tab page |
| not | `music.youtube.com/` and `/library` | `youtube:tab` |
| not | `/embed/live_stream?channel=UC...` (channel live, not an item) | `_redirect.py:63` |
| not | `/watch?v=<1-10 chars>` (truncated link) | `_mistakes.py:58` |
| not | `youtube.com/source/<11>/shorts` (audio pivot) | `_redirect.py:183`, deliberately excluded as obscure |

### Instagram

| Kind | Shape | Evidence |
|---|---|---|
| single | `/p/<shortcode>` | `instagram.py:278` |
| single | `/reel/<shortcode>`, `/reels/<shortcode>` | `instagram.py:278` (`reels?`) |
| single | `/tv/<shortcode>` | `instagram.py:278` |
| single | `/<username>/p/<shortcode>` and the same for reel/reels/tv | `instagram.py:278`, the `(?:/(?!share/)[^/?#]+)?` segment |
| not | `/<username>` (profile) | `instagram.py:634` |
| not | `/explore/`, `/explore/tags/<tag>` | `instagram.py:668`; `/explore/` itself matches the *user* regex, which is why "yt-dlp accepted it" is not evidence of media |
| not | `/reels/` (the feed) | matches `InstagramUserIE` as a "username", `instagram.py:634` |
| not | `/reels/audio/<id>` (audio page) | explicit `(?!/audio/)`, `instagram.py:278` |
| not | `/stories/<user>/<id>`, `/stories/highlights/<id>` | `instagram.py:703` |
| not | `/share/<token>/`, `/share/reel/<shortcode>/` | explicit `(?!share/)`, `instagram.py:278` |
| not | `/about/`, `/accounts/login/` | `InstagramUserIE` treats `/about/` as a username; no media extractor |

### TikTok

| Kind | Shape | Evidence |
|---|---|---|
| single | `/@<user>/video/<digits>` | `tiktok.py:709` |
| single | `/share/video/<digits>` | `tiktok.py:709` |
| single | `/embed/<digits>`, `www.tiktokv.com/...` | `tiktok.py:709` (`tiktokv?`) |
| single | `vm.tiktok.com/<token>`, `vt.tiktok.com/<token>`, `tiktok.com/t/<token>` | `tiktok.py:1512`, resolves by HEAD then redirects (`:1566-1571`) |
| not | `/@<user>` (profile) | `tiktok.py:1020` |
| not | `/@<user>/live` (ongoing stream) | `tiktok.py:1575` |
| not | `/@<user>/photo/<digits>` (photo post) | **no extractor**; falls to generic |
| not | `/@<user>/collection/<name>-<digits>` | `tiktok.py:1315` (playlist) |
| not | `/tag/<tag>` | `tiktok.py:1287` |
| not | `/music/<slug>-<digits>` | `tiktok.py:1243` |
| not | `/sticker/<slug>-<digits>` | `tiktok.py:1267` |
| not | `/foryou`, `/following`, `/explore`, `/discover/<x>`, `/search?q=` | generic only |
| not | `m.tiktok.com/@<user>/video/<digits>` | host must be `www.tiktokv?.com`, so `m.` falls to generic |

### X / Twitter

| Kind | Shape | Evidence |
|---|---|---|
| single | `x.com/<user>/status/<digits>` | `twitter.py:271` |
| single | `twitter.com/<user>/status/<digits>`, `mobile.twitter.com/...`, `m.twitter.com/...` | `twitter.py:38` |
| single | `x.com/i/web/status/<digits>`, `x.com/i/status/<digits>` | `twitter.py:271` (`(?:i/web|[^/?#]+)/status`) |
| single | `x.com/statuses/<digits>` (legacy, no user segment) | `twitter.py:271` |
| single | same URL with `/video/1` or `/photo/1` suffix | `twitter.py:271` |
| not | `x.com/<user>`, `/with_replies`, `/followers`, `/media` | generic only |
| not | `/hashtag/<tag>`, `/explore`, `/home`, `/notifications`, `/search` | generic only |
| not | `/i/communities/<id>`, `/i/lists/<id>`, `/i/flow/login` | generic only |
| not | `/i/spaces/<id>` (audio space, not a downloadable item shaped like a status) | `twitter.py:1599` |
| not | `/i/broadcasts/<id>` | `twitter.py:1453` |
| not | `t.co/<token>` | `twitter.py:1772`; it is a generic shortener and can point anywhere |

### Facebook

| Kind | Shape | Evidence |
|---|---|---|
| single | `/reel/<digits>` | `facebook.py:959` |
| single | `/watch/?v=<digits>`, `/watch?v=<digits>`, `/watch/?v=<id>&ref=...` | `facebook.py:47-48` |
| single | `/watch/live/?v=<digits>` (a stored live video, still one item) | `facebook.py:47` |
| single | `/video.php?v=`, `/video/video.php?v=`, `/video/embed?v=` | `facebook.py:41-46` |
| single | `/story.php?story_fbid=<id>`, `/permalink.php?story_fbid=<id>` | `facebook.py:41-48` |
| single | `/<user>/videos/<digits>`, `/<user>/videos/<slug>/<digits>` | `facebook.py:49` |
| single | `/<user>/posts/<digits>` | `facebook.py:50` |
| single | `/groups/<group>/posts/<id>`, `/groups/<group>/permalink/<id>` | `facebook.py:52` |
| single | `/watchparty/<id>` | `facebook.py:53` |
| not | `/`, `/<page>` | generic only |
| not | `/watch`, `/watch/`, `/watch/?ref=home` (watch home, no video id) | `facebook.py:47-48` requires `v=`/`video_id=`/`story_fbid=` |
| not | `/<user>/videos/` (the person's video tab) | needs a trailing id |
| not | `/reels/<digits>` (plural) | only `reel/` exists, `facebook.py:959` |
| not | `/share/v/<token>/`, `/share/r/<token>/` | no extractor, generic only |
| not | `/photo.php?fbid=` (photo, no video param) | `facebook.py:43` requires one of the three video params |
| not | `/hashtag/<tag>`, `/<page>/likes/`, `/pages/category/...` | generic only |
| not | `fb.watch/<token>` | **no extractor**; generic only, redirect target unknown |

### Bilibili

| Kind | Shape | Evidence |
|---|---|---|
| single | `/video/BV<alnum>` (any case) | `bilibili.py:372` (`[aAbB][vV]`) |
| single | `/video/av<digits>` (any case) | same regex; `:740-743` maps `AV` prefix to `aid` |
| single | `/video/BV<alnum>?p=<n>` (one part of a multi-part video) | same URL shape |
| single | `/bangumi/play/ep<digits>` (one episode) | `bilibili.py:903` |
| single | `/audio/au<digits>` (one track) | `bilibili.py:1953` |
| single | `/festival/<slug>?bvid=BV<alnum>` | `bilibili.py:372` |
| not | `/` , `/anime/`, `/v/popular/*`, `/account/history` | category/home extractors or generic, `bilibili.py:1822` |
| not | `space.bilibili.com/<mid>` (user space) | `bilibili.py:1338`, a space is a list |
| not | `/list/<id>`, `/list/watchlater?bvid=...`, `/medialist/detail/ml<id>` | `bilibili.py:1689`, `:1667`, `:1617` |
| not | `/bangumi/play/ss<digits>` (whole season) | `bilibili.py:1143`, a season is a playlist |
| not | `/audio/am<digits>` (album) | `bilibili.py:2023` |
| not | `/read/cv<id>`, `t.bilibili.com/<id>` (text posts) | `bilibili.py:2076` (opus/dynamic) |
| not | `live.bilibili.com/<room>` (ongoing room) | `bilibili.py:2586` |
| not | `search.bilibili.com/...` | search |
| not | `m.bilibili.com/...` | regex is `(?:www\.)?`, `bilibili.py:372` |

### Douyin

| Kind | Shape | Evidence |
|---|---|---|
| single | `/video/<digits>` | `tiktok.py:1372` |
| not | `/note/<digits>` (photo/note post) | **no extractor**; generic only |
| not | `/user/<sec_uid>` | generic only |
| not | `/`, `/discover`, `/hot`, `/follow`, `/search/<q>` | generic only |
| not | `/share/video/<digits>` | generic only |
| not | `iesdouyin.com/share/video/<digits>` | generic only |

---

## Ambiguous cases and the reasonable behaviour

Rule of thumb used: offer a URL when a person clicking it expects *one thing to
download*. When the page happens to hold several files (carousel, anthology),
still offer it and let the queue hold several files, because that is what the
person asked for. Reject when the page is navigation (profile, feed, season,
album, tag).

| # | Case | What yt-dlp says | Offer it? | Why |
|---|---|---|---|---|
| 1 | `watch?v=ID&list=PL...` | not a single video (`_video.py:1922-1929`), routed to `youtube:tab` | **Yes** | A person pointing at a video expects that video. The app runs `noplaylist: True` (`utils/ydl_opts.py:86`), so the download takes one video. This is a deliberate, documented divergence from yt-dlp's classifier. |
| 2 | `playlist?list=PL...` | playlist (`_tab.py:1082`) | No | Pure navigation, no video selected. |
| 3 | Instagram `/p/<shortcode>` that is a carousel | playlist of 2..10 items for multi-video posts | **Yes** | The post is the unit; the download yields all its files. |
| 4 | Instagram `/stories/<user>/<id>` | the extractor ignores the item id and requests the user's whole reel (`instagram.py:740-746`) | No | Even with an id you do not get that item, you get the reel. |
| 5 | Bilibili `/video/BV...` with several `p` parts (anthology) | playlist with N parts (test fixture at `bilibili.py:414-421`) | **Yes** | Same reasoning as the carousel. |
| 6 | Bilibili `/bangumi/play/ss<id>` | the season (`bilibili.py:1143`) | No | A season is a container of episodes; `ep` is the item. |
| 7 | `x.com/<user>/status/<id>` with no video in it | extractor accepts, then finds no video | **Yes** | The URL shape cannot tell you whether the tweet has media. Scan-time precision is impossible here; the download fails with a clean "no video" error, which `sites/errors.py` already reports. |
| 8 | TikTok `/@<user>/photo/<id>` | no extractor, generic only | No | Not a video; yt-dlp cannot download it either. Offering it would queue a job that always fails. |
| 9 | Douyin `/note/<id>` | no extractor, generic only | No | Same as above. Note the current `core/native.py` pattern accepts it. |
| 10 | `vm.tiktok.com/<token>`, `vt.tiktok.com/<token>`, `tiktok.com/t/<token>` | `TikTokVMIE` resolves via HEAD then redirects (`tiktok.py:1566-1571`) | **Yes** | yt-dlp handles the resolution itself; the shape is unambiguous (these domains only carry video tokens). |
| 11 | `t.co/`, `fb.watch/`, `b23.tv/`, Instagram `/share/` | no dedicated extractor; generic at best | No | The token carries no information about the target and the generic extractor is best-effort. |
| 12 | YouTube `/@handle` (the channel landing page autoplays a video) | `youtube:tab` | No | The URL identifies a channel. |
| 13 | YouTube `/live/<id>` and Facebook `/watch/live/?v=` | `YoutubeIE` / `FacebookIE`, one item each | **Yes** | Both identify one stored or currently-live video by id, not an open-ended room. Contrast with `/@user/live` and `live.bilibili.com/<room>`, which are rooms with no id for a finished recording. |

---

## The patterns

Anchored, tested against the full `url.href`. `new RegExp(pattern).test(href)` in
the popup and `re.match(pattern, url)` in Python behave the same for these
constructs (no lookbehind, no named groups).

Notes that matter for portability:

- `url.href` lowercases the host but preserves path case, so only Bilibili needs
  case classes (`[aAbB][vV]`).
- JS `\w` is ASCII-only, Python's is Unicode-aware. Stricter in JS, which is the
  safe direction for ids and handles. No handle pattern is used here anyway.
- The popup already picks the platform by hostname first
  (`extension/popup.js:66-71`, `sites/cookies.py:9-17`), so these patterns only
  have to prove the *shape*. The host is repeated in each pattern so the same
  list is safe if used from `core/native.py:is_media_url`, which does not
  pre-filter by host.

```python
MEDIA_PATTERNS = {
    "youtube": (
        r"^https?://(?:[\w-]+\.)*youtube\.com/watch\?(?:[^#]*&)?v=[\w-]{11}",
        r"^https?://(?:[\w-]+\.)*youtube\.com/(?:shorts|live|embed|v|e)/(?!videoseries|live_stream)[\w-]{11}",
        r"^https?://youtu\.be/[\w-]{11}",
        r"^https?://(?:[\w-]+\.)*youtube\.com/clip/[\w-]+",
    ),
    "instagram": (
        r"^https?://(?:www\.)?instagram\.com/(?:(?!share/)[^/?#]+/)?(?:p|tv|reels?)/(?!audio/)[\w-]+",
    ),
    "tiktok": (
        r"^https?://www\.tiktokv?\.com/(?:embed|(?:share|@[\w.-]+)/video)/\d+",
        r"^https?://(?:vm|vt)\.tiktok\.com/\w+",
        r"^https?://(?:www\.)?tiktok\.com/t/\w+",
    ),
    "twitter": (
        r"^https?://(?:(?:www|m|mobile)\.)?(?:twitter|x)\.com/(?:(?:i/web|[^/?#]+)/status|statuses)/\d+",
    ),
    "facebook": (
        r"^https?://(?:[\w-]+\.)?facebook\.com/reel/\d+",
        r"^https?://(?:[\w-]+\.)?facebook\.com/(?:permalink\.php|video/video\.php|video\.php|video/embed|story\.php|watch(?:/live)?/?)\?(?:[^#]*&)?(?:v|video_id|story_fbid)=(?:pfbid\w+|\d+)",
        r"^https?://(?:[\w-]+\.)?facebook\.com/[^/?#]+/videos/(?:[^/?#]+/)?(?:pfbid\w+|\d+)",
        r"^https?://(?:[\w-]+\.)?facebook\.com/[^/?#]+/posts/(?:pfbid\w+|\d+)",
        r"^https?://(?:[\w-]+\.)?facebook\.com/groups/[^/?#]+/(?:permalink|posts)/(?:pfbid\w+|\d+)",
        r"^https?://(?:[\w-]+\.)?facebook\.com/watchparty/(?:pfbid\w+|\d+)",
    ),
    "bilibili": (
        r"^https?://(?:www\.)?bilibili\.com/video/[aAbB][vV]\w+",
        r"^https?://(?:www\.)?bilibili\.com/bangumi/play/ep\d+",
        r"^https?://(?:www\.)?bilibili\.com/audio/au\d+",
        r"^https?://(?:www\.)?bilibili\.com/festival/[^/?#]+\?(?:[^#]*&)?bvid=[aAbB][vV]\w+",
    ),
    "douyin": (
        r"^https?://(?:www\.)?douyin\.com/video/\d+",
    ),
}
```

Where each pattern comes from, one line each:

| Pattern | Ported from |
|---|---|
| youtube 1 | `_video.py:86-120`, minus the `list=` rejection at `:1922-1929` (see ambiguity 1) |
| youtube 2 | `_video.py:99` including its `(?!videoseries\|live_stream)` guard |
| youtube 3 | `_video.py:108` |
| youtube 4 | `_clip.py:8` |
| instagram | `instagram.py:278`, keeping both negative lookaheads verbatim |
| tiktok 1 | `tiktok.py:709` |
| tiktok 2 | `tiktok.py:1512` |
| tiktok 3 | `tiktok.py:1512` (`(?:www\.)tiktok\.com/t/`) |
| twitter | `twitter.py:38` + `:271` merged |
| facebook 1 | `facebook.py:959` |
| facebook 2 | `facebook.py:41-48` |
| facebook 3-6 | `facebook.py:49-53`, with the id class from `:57` |
| bilibili 1 | `bilibili.py:372`, `:740-743` for the `av` prefix |
| bilibili 2 | `bilibili.py:903` |
| bilibili 3 | `bilibili.py:1953` |
| bilibili 4 | `bilibili.py:372` (festival branch) |
| douyin | `tiktok.py:1372` |

### Delta against the current `core/native.py:27-57`

Read-only review, nothing changed. Ordered by user impact:

| Current behaviour | Problem | Should be |
|---|---|---|
| Instagram `(?:p\|reel\|reels\|tv)/[\w-]+` | accepts `/reels/audio/<id>`, which yt-dlp explicitly rejects (`instagram.py:278`). Verified: `is_media_url` returns True for it | add `(?!audio/)` |
| Instagram `(?:p\|reel\|reels\|tv)` | misses `/<username>/p/<shortcode>`, a real share shape (`instagram.py:278`) | allow the optional user segment |
| Facebook `watch/?(?:\?...)?$` | accepts bare `/watch/` and `/watch/` with no `v=`. Verified True for `https://www.facebook.com/watch/` | require one of the three params, `facebook.py:47-48` |
| Facebook same pattern with `$` | rejects `watch/?v=<id>&ref=sharing`. Verified False | drop the `$`, allow trailing params |
| Facebook | misses `/groups/<g>/posts/<id>`, `/<user>/posts/<id>`, `permalink.php`, `watchparty/<id>` | add, `facebook.py:50-53` |
| Twitter `(?:[^/]+\|i)/status` | misses `x.com/i/web/status/<id>` and `x.com/statuses/<id>`. Verified False for the first | use `twitter.py:271` verbatim |
| TikTok `@[^/]+/video/\d+` | misses `/share/video/<id>`, `/embed/<id>`, `/t/<token>`, `www.tiktokv.com` | see patterns |
| Douyin `(?:video\|note)` | `note` has no extractor (`tiktok.py:1372` is `/video/` only); it always fails | drop `note` |
| Bilibili `(?:BV[\w]+\|av\d+)` | rejects lowercase `bv` and uppercase `AV`, which yt-dlp accepts (`bilibili.py:372`); misses `/audio/au<id>` and `/festival/...?bvid=` | case classes, add the two shapes |
| YouTube `shorts\|live\|embed\|v` with `[\w-]+` | accepts `/embed/live_stream?channel=...` (11 chars) as if it were an id | `{11}` plus the two negative lookaheads |
| YouTube watch | accepts `list=` links, contradicting `_video.py:1922` | keep, this is the intended divergence |

---

## Test cases

Synthetic only. All of the following were executed against the patterns above
with Node 24 (`new RegExp(p).test(url)`): **66 must-match, 119 must-reject, 0
failures**.

### Must match

| Platform | URL |
|---|---|
| youtube | `https://www.youtube.com/watch?v=aaaaaaaaaaa` |
| youtube | `https://www.youtube.com/watch?v=aaaaaaaaaaa&t=10s` |
| youtube | `https://www.youtube.com/watch?app=desktop&v=aaaaaaaaaaa` |
| youtube | `https://www.youtube.com/watch?v=aaaaaaaaaaa&list=PLbbbbbbbbbb` |
| youtube | `https://m.youtube.com/watch?v=aaaaaaaaaaa` |
| youtube | `https://music.youtube.com/watch?v=aaaaaaaaaaa` |
| youtube | `https://www.youtube.com/shorts/aaaaaaaaaaa` |
| youtube | `https://www.youtube.com/shorts/aaaaaaaaaaa?feature=share` |
| youtube | `https://www.youtube.com/live/aaaaaaaaaaa` |
| youtube | `https://www.youtube.com/embed/aaaaaaaaaaa` |
| youtube | `https://www.youtube.com/v/aaaaaaaaaaa` |
| youtube | `https://youtu.be/aaaaaaaaaaa` |
| youtube | `https://youtu.be/aaaaaaaaaaa?si=xyz` |
| youtube | `https://www.youtube.com/clip/Ugbbbbbbbbbb` |
| instagram | `https://www.instagram.com/p/AAAbbb11111/` |
| instagram | `https://www.instagram.com/p/AAAbbb11111/?igsh=xyz` |
| instagram | `https://www.instagram.com/reel/AAAbbb11111/` |
| instagram | `https://www.instagram.com/reels/AAAbbb11111/` |
| instagram | `https://www.instagram.com/tv/AAAbbb11111/` |
| instagram | `https://www.instagram.com/someone/p/AAAbbb11111/` |
| instagram | `https://www.instagram.com/someone/reel/AAAbbb11111/` |
| instagram | `https://instagram.com/p/AAAbbb11111/` |
| tiktok | `https://www.tiktok.com/@someone/video/123456789` |
| tiktok | `https://www.tiktok.com/@someone/video/123456789?is_from_webapp=1` |
| tiktok | `https://www.tiktok.com/@some.one/video/123456789` |
| tiktok | `https://www.tiktok.com/share/video/123456789` |
| tiktok | `https://www.tiktok.com/embed/123456789` |
| tiktok | `https://www.tiktokv.com/@someone/video/123456789` |
| tiktok | `https://vm.tiktok.com/Zabcdef/` |
| tiktok | `https://vt.tiktok.com/Zabcdef/` |
| tiktok | `https://www.tiktok.com/t/Zabcdef/` |
| twitter | `https://x.com/someone/status/1234567890123456789` |
| twitter | `https://twitter.com/someone/status/1234567890123456789` |
| twitter | `https://mobile.twitter.com/someone/status/1234567890123456789` |
| twitter | `https://m.twitter.com/someone/status/1234567890123456789` |
| twitter | `https://x.com/i/web/status/1234567890123456789` |
| twitter | `https://x.com/i/status/1234567890123456789` |
| twitter | `https://x.com/statuses/1234567890123456789` |
| twitter | `https://x.com/someone/status/1234567890123456789/video/1` |
| twitter | `https://x.com/someone/status/1234567890123456789?s=20` |
| facebook | `https://www.facebook.com/reel/1234567890` |
| facebook | `https://www.facebook.com/watch/?v=1234567890` |
| facebook | `https://www.facebook.com/watch?v=1234567890` |
| facebook | `https://www.facebook.com/watch/?v=1234567890&ref=sharing` |
| facebook | `https://www.facebook.com/watch/live/?v=1234567890` |
| facebook | `https://www.facebook.com/video.php?v=1234567890` |
| facebook | `https://www.facebook.com/video/video.php?v=1234567890` |
| facebook | `https://www.facebook.com/video/embed?v=1234567890` |
| facebook | `https://www.facebook.com/story.php?story_fbid=1234567890&id=123` |
| facebook | `https://www.facebook.com/permalink.php?story_fbid=pfbid0abc&id=123` |
| facebook | `https://www.facebook.com/someone/videos/1234567890/` |
| facebook | `https://www.facebook.com/someone/videos/sometitle/1234567890/` |
| facebook | `https://www.facebook.com/someone/posts/1234567890` |
| facebook | `https://www.facebook.com/groups/somegroup/posts/1234567890/` |
| facebook | `https://www.facebook.com/groups/somegroup/permalink/1234567890/` |
| facebook | `https://www.facebook.com/watchparty/1234567890` |
| facebook | `https://m.facebook.com/reel/1234567890` |
| bilibili | `https://www.bilibili.com/video/BV0000000001` |
| bilibili | `https://www.bilibili.com/video/BV0000000001/?p=2` |
| bilibili | `https://www.bilibili.com/video/BV0000000001?spm_id_from=333` |
| bilibili | `https://www.bilibili.com/video/av0000001` |
| bilibili | `https://www.bilibili.com/bangumi/play/ep123456` |
| bilibili | `https://www.bilibili.com/audio/au12345` |
| bilibili | `https://www.bilibili.com/festival/somefest?bvid=BV0000000001` |
| douyin | `https://www.douyin.com/video/1234567890123456789` |
| douyin | `https://www.douyin.com/video/1234567890123456789?previous_page=web_code_link` |

### Must not match

| Platform | URL | Why |
|---|---|---|
| youtube | `https://www.youtube.com/` | recommended feed |
| youtube | `https://www.youtube.com/@somechannel` | channel |
| youtube | `https://www.youtube.com/@somechannel/videos` | channel tab |
| youtube | `https://www.youtube.com/@somechannel/shorts` | channel tab |
| youtube | `https://www.youtube.com/@somechannel/playlists` | channel tab |
| youtube | `https://www.youtube.com/@somechannel/live` | channel live tab |
| youtube | `https://www.youtube.com/channel/UCbbbbbbbbbbbbbbbbbbbbbb` | channel |
| youtube | `https://www.youtube.com/c/somechannel` | channel |
| youtube | `https://www.youtube.com/user/someuser` | channel |
| youtube | `https://www.youtube.com/feed/subscriptions` | feed |
| youtube | `https://www.youtube.com/feed/trending` | feed |
| youtube | `https://www.youtube.com/feed/you` | feed |
| youtube | `https://www.youtube.com/playlist?list=PLbbbbbbbbbb` | playlist |
| youtube | `https://www.youtube.com/watch?list=PLbbbbbbbbbb` | playlist, no video id |
| youtube | `https://www.youtube.com/watch` | no id |
| youtube | `https://www.youtube.com/watch?v=abc` | truncated id |
| youtube | `https://www.youtube.com/shorts` | shorts feed |
| youtube | `https://www.youtube.com/shorts/` | shorts feed |
| youtube | `https://www.youtube.com/hashtag/sometag` | hashtag |
| youtube | `https://www.youtube.com/results?search_query=abc` | search |
| youtube | `https://www.youtube.com/premium` | marketing page |
| youtube | `https://www.youtube.com/about/` | policy page |
| youtube | `https://www.youtube.com/t/terms` | policy page |
| youtube | `https://www.youtube.com/account` | account |
| youtube | `https://www.youtube.com/upload` | upload |
| youtube | `https://studio.youtube.com/channel/UCbbbbbbbbbbbbbbbbbbbbbb` | studio |
| youtube | `https://studio.youtube.com/video/aaaaaaaaaaa/edit` | studio |
| youtube | `https://music.youtube.com/` | music home |
| youtube | `https://music.youtube.com/library` | library |
| youtube | `https://music.youtube.com/search?q=abc` | search |
| youtube | `https://www.youtube.com/embed/live_stream?channel=UCbbbbbbbbbbbbbbbbbbbbbb` | channel live, not an item |
| instagram | `https://www.instagram.com/` | home |
| instagram | `https://www.instagram.com/someone/` | profile |
| instagram | `https://www.instagram.com/someone` | profile |
| instagram | `https://www.instagram.com/explore/` | explore |
| instagram | `https://www.instagram.com/explore/tags/sometag/` | tag |
| instagram | `https://www.instagram.com/reels/` | reels feed |
| instagram | `https://www.instagram.com/reels/audio/1234567890/` | audio page |
| instagram | `https://www.instagram.com/stories/someone/123456789/` | story |
| instagram | `https://www.instagram.com/stories/highlights/123456789/` | highlight |
| instagram | `https://www.instagram.com/share/AAAbbb11111/` | share wrapper |
| instagram | `https://www.instagram.com/share/reel/AAAbbb11111/` | share wrapper |
| instagram | `https://www.instagram.com/about/` | policy page |
| instagram | `https://www.instagram.com/accounts/login/` | login |
| tiktok | `https://www.tiktok.com/` | home |
| tiktok | `https://www.tiktok.com/@someone` | profile |
| tiktok | `https://www.tiktok.com/@someone/` | profile |
| tiktok | `https://www.tiktok.com/@someone/live` | live room |
| tiktok | `https://www.tiktok.com/@someone/photo/123456789` | photo post |
| tiktok | `https://www.tiktok.com/@someone/collection/somename-123456789` | collection |
| tiktok | `https://www.tiktok.com/tag/sometag` | tag |
| tiktok | `https://www.tiktok.com/music/sometrack-123456789` | sound |
| tiktok | `https://www.tiktok.com/sticker/somesticker-123456789` | effect |
| tiktok | `https://www.tiktok.com/foryou` | feed |
| tiktok | `https://www.tiktok.com/following` | feed |
| tiktok | `https://www.tiktok.com/explore` | feed |
| tiktok | `https://www.tiktok.com/discover/sometopic` | discover |
| tiktok | `https://www.tiktok.com/search?q=abc` | search |
| tiktok | `https://www.tiktok.com/@someone/video/abc` | non-numeric id |
| tiktok | `https://m.tiktok.com/@someone/video/123456789` | host not supported by yt-dlp either |
| twitter | `https://x.com/` | home |
| twitter | `https://x.com/someone` | profile |
| twitter | `https://x.com/someone/with_replies` | profile tab |
| twitter | `https://x.com/someone/followers` | profile tab |
| twitter | `https://x.com/someone/media` | profile tab |
| twitter | `https://x.com/hashtag/sometag` | hashtag |
| twitter | `https://x.com/explore` | explore |
| twitter | `https://x.com/home` | home |
| twitter | `https://x.com/notifications` | notifications |
| twitter | `https://x.com/search?q=abc` | search |
| twitter | `https://x.com/i/communities/1234567890` | community |
| twitter | `https://x.com/i/lists/1234567890` | list |
| twitter | `https://x.com/i/flow/login` | login |
| twitter | `https://x.com/i/spaces/1abcdefghijkl` | space |
| twitter | `https://t.co/abcdef` | shortener |
| facebook | `https://www.facebook.com/` | home |
| facebook | `https://www.facebook.com/someone` | profile |
| facebook | `https://www.facebook.com/somepage` | page |
| facebook | `https://www.facebook.com/watch` | watch home |
| facebook | `https://www.facebook.com/watch/` | watch home |
| facebook | `https://www.facebook.com/watch/?ref=home` | watch home, no id |
| facebook | `https://www.facebook.com/watch/live/` | live home, no id |
| facebook | `https://www.facebook.com/someone/videos/` | video tab, no id |
| facebook | `https://www.facebook.com/reels/1234567890` | plural form, unsupported |
| facebook | `https://www.facebook.com/share/v/abcdef/` | share wrapper |
| facebook | `https://www.facebook.com/share/r/abcdef/` | share wrapper |
| facebook | `https://www.facebook.com/hashtag/sometag` | hashtag |
| facebook | `https://www.facebook.com/photo.php?fbid=123&set=a.456` | photo, no video param |
| facebook | `https://www.facebook.com/someone.likes/` | profile tab |
| facebook | `https://www.facebook.com/pages/category/Brand/Some-Page-123/` | page |
| facebook | `https://fb.watch/abcdef/` | shortener, no extractor |
| bilibili | `https://www.bilibili.com/` | home |
| bilibili | `https://space.bilibili.com/123456` | user space |
| bilibili | `https://space.bilibili.com/123456/video` | user space |
| bilibili | `https://space.bilibili.com/123456/dynamic` | user space |
| bilibili | `https://www.bilibili.com/list/123456` | playlist |
| bilibili | `https://www.bilibili.com/list/watchlater?bvid=BV0000000001` | watch later |
| bilibili | `https://www.bilibili.com/medialist/detail/ml123456` | favourites |
| bilibili | `https://www.bilibili.com/bangumi/play/ss12345` | season |
| bilibili | `https://www.bilibili.com/audio/am12345` | album |
| bilibili | `https://www.bilibili.com/read/cv123456` | article |
| bilibili | `https://www.bilibili.com/v/popular/all` | category |
| bilibili | `https://www.bilibili.com/account/history` | account |
| bilibili | `https://www.bilibili.com/anime/` | index |
| bilibili | `https://t.bilibili.com/1234567890` | dynamic post |
| bilibili | `https://live.bilibili.com/12345` | live room |
| bilibili | `https://search.bilibili.com/all?keyword=abc` | search |
| bilibili | `https://www.bilibili.com/video/` | no id |
| bilibili | `https://www.bilibili.com/video/BV` | no id |
| douyin | `https://www.douyin.com/` | home |
| douyin | `https://www.douyin.com/user/MS4wLjABAAAA` | profile |
| douyin | `https://www.douyin.com/note/1234567890123456789` | note, no extractor |
| douyin | `https://www.douyin.com/discover` | discover |
| douyin | `https://www.douyin.com/hot` | hot |
| douyin | `https://www.douyin.com/follow` | feed |
| douyin | `https://www.douyin.com/search/abc` | search |
| douyin | `https://www.douyin.com/share/video/1234567890123456789` | share wrapper |
| douyin | `https://www.iesdouyin.com/share/video/1234567890123456789/` | share wrapper |
| douyin | `https://www.douyin.com/video/abc` | non-numeric id |

---

## Confidence, and what was not checked

**Confidence: high** for the shape classification of all seven platforms. Every
row traces to a `_VALID_URL` or a `suitable()` override read in the installed
yt-dlp, and the whitelist was executed against 185 URLs with zero mismatches.

Two deliberate divergences from yt-dlp, both argued in the ambiguity table: the
`list=` watch URL (accepted) and the missing `/@user/live`, `photo`, `note`
shapes (rejected because no extractor exists).

**Not checked:**

- No live network request was made. Nothing here confirms a video still exists,
  is public, or is region-locked. That failure class is the download step's, not
  the scanner's.
- The `list=` decision rests on `noplaylist: True` (`utils/ydl_opts.py:86`).
  If that option is ever removed, `watch?v=ID&list=PL...` would start queueing a
  whole playlist, and the first youtube pattern should be tightened then.
- Mobile and regional hosts not covered by the extractor regexes were not
  researched (`m.bilibili.com`, `m.douyin.com`). They are excluded here because
  yt-dlp excludes them, and `GenericIE` backstop behaviour on those hosts was
  not verified.
- A frozen build bundles its own yt-dlp and cannot update it (`AGENTS.md`,
  "The yt-dlp Python API is not the CLI"), so these patterns describe
  2026.08.19. If upstream adds a Douyin note or TikTok photo extractor, the
  whitelist will be too strict, not too loose, which is the safe direction.
