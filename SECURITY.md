# Security Policy

## Reporting a vulnerability

Please **do not** report security issues through public GitHub issues.

Report them privately using GitHub's
[private vulnerability reporting](https://github.com/petra-dot/socialclip-downloader/security/advisories/new)
(Security tab → Report a vulnerability). If you cannot use that, open a minimal
issue asking for a private channel and do not include details.

Useful information to include:

- what the issue is and where it lives (file, command, or workflow),
- steps to reproduce,
- the impact you believe it has,
- any suggested fix.

You can expect an acknowledgement within about a week. This is a
volunteer-maintained project, so please be patient.

## Scope

This project is a local desktop application and command-line tool. It has no
server, no accounts, and no telemetry. In-scope examples:

- a path or command injection reachable from a downloaded file name or URL,
- a way to make the tool read or exfiltrate a cookies file or other credential,
- a release or CI/workflow weakness that could let a third party ship code,
- a dependency issue that this project's code makes exploitable.

Out of scope:

- the security posture of the sites you download from, or of `yt-dlp` itself
  (report those upstream to the respective projects),
- anything that requires the attacker to already control your machine or your
  account,
- rate limiting, bot detection, or access controls you are trying to circumvent.

## Handling of credentials

The application reads cookie files for platforms that require authentication.
These files are treated as secrets:

- they are excluded by `.gitignore` and never committed,
- CI runs a [gitleaks](.github/workflows/gitleaks.yml) secret scan on every push
  and pull request,
- downloaded cookie files are never uploaded anywhere by this project.

If you believe a credential has been committed to this repository, please report
it privately using the process above so it can be rotated and purged before it
is disclosed further.
