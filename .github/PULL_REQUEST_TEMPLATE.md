## What changed

<!-- One or two sentences. What does this PR do? -->

## Why

<!-- The problem it solves, or the issue it closes: "Fixes #123" -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor / internal change
- [ ] Documentation only

## Testing done

- [ ] `python -m pytest -q` passes
- [ ] `python -m flake8 . --count --select=E9,F63,F7,F82 --statistics` reports 0

If this touches the Qt interface (which is not unit-tested), describe how you
verified it by hand:

<!-- e.g. "Launched the app, added two URLs to the Queue, paused, resumed,
cancelled; the rows updated correctly." -->

## Checklist

- [ ] The change is focused on one thing
- [ ] Logic in `core/` or `utils/` has a test that asserts real behaviour
- [ ] No codec an editor rejects (VP9/AV1/HEVC/Opus/Vorbis) can appear in output
- [ ] No secrets, cookies files, or credentials are included
- [ ] Commit messages follow Conventional Commits
