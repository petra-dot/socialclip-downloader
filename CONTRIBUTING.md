# Contributing to SocialClip Downloader

Thanks for helping out. This is a small, volunteer-maintained project, so a
tidy, well-scoped pull request is appreciated far more than a large one.

## Before you start

- **Search existing [issues](https://github.com/petra-dot/socialclip-downloader/issues)**
  before opening a new one. Someone may already be on it.
- For a bug, include a clear description, the exact steps to reproduce, what you
  expected, and what happened — plus your operating system and whether you are
  running a release binary or from source.
- For a security issue, follow [SECURITY.md](SECURITY.md) instead. Do not open a
  public issue.

## Setting up

```bash
git clone https://github.com/petra-dot/socialclip-downloader.git
cd socialclip-downloader
pip install -r requirements-dev.txt   # runtime deps + pytest + flake8
```

You will also need **ffmpeg** on your `PATH` to exercise downloads and
conversions, or point `SOCIALCLIP_FFMPEG` at it.

## Making a change

1. Create a branch off `main` (`feat/...`, `fix/...`, or `chore/...`).
2. Keep the change focused. One logical change per pull request is much easier
   to review than several bundled together.
3. Add or update tests for any behavior you change (see below).
4. Run the checks before pushing:

   ```bash
   python -m pytest -q
   python -m flake8 . --count --select=E9,F63,F7,F82 --statistics
   ```

5. Open the pull request and describe **what** changed and **why**.

## Where things live

The codebase is split so that logic can be tested without a display:

- **`core/`** is Qt-free by rule. Download orchestration, conversion planning,
  the format registry, the queue, and the doctor report all live here, and this
  is where most logic changes belong. `tests/test_core_isolation.py` enforces
  that `core/` never imports PyQt5.
- **`ui/`** and **`workers/`** are the PyQt5 layer. Workers are thin adapters
  that call into `core/` and report progress through Qt signals.
- **`sites/`** holds platform detection, cookie lookup, and error classification.
- **`utils/`** holds ffmpeg discovery, filename handling, and yt-dlp options.

See [AGENTS.md](AGENTS.md) for the full layout and the project's conventions.

## Testing expectations

- Logic in `core/` and `utils/` must be covered by `pytest` tests that assert
  real behavior. Prefer pure functions with injectable dependencies (a `runner`
  or `which` parameter) so tests do not touch the network or ffmpeg.
- The Qt interface is not unit-tested; describe how you verified a UI change
  manually in your pull request instead.
- Keep the whole suite green. CI runs `pytest` and `flake8` on Python 3.9, 3.10,
  and 3.11, plus a `gitleaks` secret scan.

## Style

- Follow the existing conventions rather than introducing new ones. See
  [AGENTS.md](AGENTS.md) for the specifics (shared constants, error routing,
  the Qt-free core rule).
- Comments should explain intent where it is not obvious from the code. Avoid
  narrating what a line does.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat:`, `fix:`, `chore:`, `docs:`, ...).

## Reporting a bug well

A report that can be reproduced quickly is the single most valuable
contribution. Include:

- the command or GUI action you took,
- the exact error text (or the `--json` output, which is machine-readable),
- your OS and how you installed the app,
- the output of `socialclip doctor`, which reports ffmpeg and cookie status.
