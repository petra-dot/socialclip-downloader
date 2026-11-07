# Firefox installation options for a self-distributed extension

Research date: 2026-11-08. Current stable Firefox is 159; 160 ships 2026-11-10
([Firefox 160 admin release notes](https://firefox-admin-docs.mozilla.org/release-notes/version/firefox-160/)).

Subject: `socialclip@petra-dot`, plain MV3 add-on with `background.scripts`, shipped
inside the SocialClip desktop app, talking to it over native messaging.

## Short answer

For a non-technical user on ordinary release Firefox, the only free, permanent,
no-store option is **AMO unlisted signing plus "install from file"**:

1. Sign each release once on addons.mozilla.org with `channel=unlisted` (free, no
   listing, automated validation, usually minutes).
2. Ship the signed `.xpi` inside the app.
3. User installs it once through Add-ons Manager, cog menu, "Install Add-on From
   File" (or by opening the `.xpi` in Firefox).

It survives restarts, needs no administrator rights, no managed machine, and no
store listing. The only maintenance cost is re-signing whenever the extension
code changes.

Everything else fails the constraints:

* Release and Beta Firefox **ignore** `xpinstall.signatures.required` at runtime,
  so no pref trick exists there.
* Developer Edition and Nightly honour the pref (Mozilla clears the build flag for
  DevEdition), but that means asking the user to run a second, different browser.
* Profile-directory and registry sideloading are compiled out except in ESR.
* Enterprise `force_installed` works on an unmanaged PC via HKCU and needs zero
  clicks, but it brand-flags the browser as managed, still requires a signed XPI,
  and is the most policy-churn-exposed path.

## Comparison

| Method | Permanent? | Cost | User steps | Managed machine | Removal risk |
|---|---|---|---|---|---|
| Temporary install (`about:debugging`) | No, unloaded on every restart ([doc](https://extensionworkshop.com/documentation/develop/temporary-installation-in-firefox/), updated 2026-10-18) | $0 | 5+ clicks, and repeats after every restart | No | N/A, it never persists |
| Signed unlisted XPI, install from file | Yes, normal Add-ons Manager entry ([doc](https://extensionworkshop.com/documentation/publish/install-self-distributed/), 2026-10-18) | $0 (AMO account, [no fee documented](https://extensionworkshop.com/documentation/publish/developer-accounts/)) | 3 to 4 clicks, once per shipped version | No | Low. Mozilla can still block/disable any add-on at any time ([policy](https://extensionworkshop.com/documentation/publish/signing-and-distribution-overview/)) |
| Policy `force_installed` (HKCU or `policies.json`) | Yes, auto-installed and re-installed | $0 | 0 after the app writes the policy | No. HKCU is read on any PC ([source](https://searchfox.org/mozilla-central/source/toolkit/components/enterprisepolicies/EnterprisePoliciesParent.sys.mjs)) | Medium. Requires a signed XPI anyway; most exposed to policy changes, e.g. `DisableLocalPolicies` in Fx 155 |
| Dev Edition / Nightly with `xpinstall.signatures.required=false` | Yes, but only inside that browser install | $0 | Install a second browser, toggle pref, install add-on | No | Medium-high. Switching back to release disables the add-on; DevEdition exemption is a build-config detail Mozilla can drop |
| Profile-dir or registry sideload | **No** on release/beta (only ESR) | $0 | Copy a file, then probably still enable it | No | High. Already removed everywhere except ESR |

## Q1. Can release Firefox install an unsigned extension?

No. Three independent layers, all current:

**Policy documentation.** "Extensions and themes need to be signed by Mozilla
before they can be installed in release and beta versions of Firefox. Unsigned
extensions can be installed in the Developer Edition, Nightly, and ESR versions of
Firefox, after toggling the `xpinstall.signatures.required` preference in
about:config. To use this feature your extension must have an add-on ID."
([Signing and distribution overview](https://extensionworkshop.com/documentation/publish/signing-and-distribution-overview/),
last updated 2024-08-21)

Same statement for enterprise deployments: "All add-ons must be signed before they
can be installed into Firefox's standard or beta versions."
([Enterprise distribution](https://extensionworkshop.com/documentation/enterprise/enterprise-distribution/),
2023-08-04)

**Build flag.** `toolkit/moz.configure` computes:

```python
@depends(milestone)
def require_signing(milestone):
    return milestone.is_release_or_beta and not milestone.is_esr
```

`milestone.is_release_or_beta` is true for any version string without an `a`
marker, so both release (`141.0`) and beta (`141.0b5`) set it
([build/moz.configure/init.configure](https://searchfox.org/mozilla-central/source/build/moz.configure/init.configure),
[milestone logic](https://searchfox.org/mozilla-central/source/toolkit/moz.configure)).

**Pref is not consulted at all.** In `AddonSettings.sys.mjs`:

```js
if (AppConstants.MOZ_REQUIRE_SIGNING && !Cu.isInAutomation) {
  makeConstant("REQUIRE_SIGNING", true);
} else {
  XPCOMUtils.defineLazyPreferenceGetter(AddonSettings, "REQUIRE_SIGNING",
    PREF_SIGNATURES_REQUIRED, false);
}
```

([AddonSettings.sys.mjs](https://searchfox.org/mozilla-central/source/toolkit/mozapps/extensions/internal/AddonSettings.sys.mjs))

So on release/beta `REQUIRE_SIGNING` is a frozen constant. The pref still appears
in `about:config` (it is set to `true` in
[firefox.js](https://searchfox.org/mozilla-central/source/browser/app/profile/firefox.js)
line 72) and can still be toggled, but **nothing reads it**, so toggling has no
effect. This is why every "set `xpinstall.signatures.required` to false" guide
fails on release Firefox.

Enforcement happens twice, both bypass-free:

* at install, `XPIInstall.sys.mjs` rejects the package with
  `"signature is required but missing"`
  ([XPIInstall.sys.mjs](https://searchfox.org/mozilla-central/source/toolkit/mozapps/extensions/internal/XPIInstall.sys.mjs));
* at every startup, `XPIDatabase.isUsableAddon()` disables an add-on that fails
  `mustSign()` ([XPIDatabase.sys.mjs](https://searchfox.org/mozilla-central/source/toolkit/mozapps/extensions/internal/XPIDatabase.sys.mjs)).
  Signatures are also re-verified periodically, once per day per the comment there.

The one exception is ESR: `MOZ_REQUIRE_SIGNING` is explicitly `false` when
`is_esr`, so ESR reads the pref (default `true`) and a user can turn it off.

## Q2. AMO signing: listed vs unlisted

| | Listed | Unlisted (self-distribution) |
|---|---|---|
| Public page on AMO | Yes | No, "cannot be publicly viewed or installed from AMO" |
| Updates | Firefox updates automatically from AMO | Only via `update_url` in the manifest, or the user reinstalls |
| Review | Automated validation, then may be queued for manual review | Same: automated validation, may be picked for manual review at any time |
| Cost | Free | Free |
| Output | Install served by AMO | Signed `.xpi` you host and ship |

Sources: [signing overview](https://extensionworkshop.com/documentation/publish/signing-and-distribution-overview/)
(2024-08-21), [self-distribution](https://extensionworkshop.com/documentation/publish/self-distribution/).

Timing and review: "Regardless of distribution method, all add-ons undergo
automated validation before they are signed. It can take up to 24 hours for your
submission to be signed and published, or longer if your submission is selected
for manual review." And: "All add-ons are subject to a manual code review at any
time after submission." In practice unlisted MV3 submissions with no risky
permissions return signed in seconds to minutes, but 24 hours is the documented
worst case for automated-only review.

The signed artifact is an ordinary ZIP (`.xpi`) with three extra entries:

* `META-INF/manifest.mf`: SHA-1/MD5 hash of every file in the package;
* `META-INF/mozilla.sf`: hash of the manifest;
* `META-INF/mozilla.rsa`: PKCS#7 detached signature over `mozilla.sf`, chaining to
  a Firefox-shipped root CA, with the certificate CN set to the add-on ID.

([Extension signing, Mozilla wiki](https://wiki.mozilla.org/Addons/Extension_Signing))

Firefox verifies all four steps on install: signature, chain to root, manifest
hash, and that every file is listed. Consequences for us: the add-on ID
(`socialclip@petra-dot`) must be in `browser_specific_settings.gecko.id` before
signing, which it already is, and any file added after signing invalidates the
package, so the XPI must be built by the signing step, not before it.

MV3 unlisted signing is supported: "For API uploads, specify channel=unlisted for
the self-distribution channel."
([Distribute MV2 and MV3 extensions](https://extensionworkshop.com/documentation/publish/distribute-manifest-versions/))
MV3 itself has been supported since Firefox 109.

## Q3. Install from file, and does it persist?

Documented flow ([Installing self-distributed extensions](https://extensionworkshop.com/documentation/publish/install-self-distributed/),
updated 2026-10-18):

1. Save the `.xpi` on the computer.
2. In Firefox, open Add-ons and themes.
3. From the settings cog, open **Install Add-on From File**.
4. Browse to the file, open it, click **Add**.
5. "The add-on now appears in the Add-on Manager's list of installed add-ons and
   is ready to use."

Persistence: this creates a normal install, not a temporary one. The contrast is
explicit in the temporary-install doc: a temporary add-on "remains installed until
you remove it or restart Firefox"
([Temporary installation](https://extensionworkshop.com/documentation/develop/temporary-installation-in-firefox/)),
while the file-install path adds the add-on to the Add-ons Manager list. Under the
hood the add-on is recorded in the profile's extension database in
`SCOPE_PROFILE` (`AddonManager.SCOPE_PROFILE = 1`), which is what is reloaded at
startup ([AddonManager.sys.mjs](https://searchfox.org/mozilla-central/source/toolkit/mozapps/extensions/AddonManager.sys.mjs),
[XPIDatabase.sys.mjs](https://searchfox.org/mozilla-central/source/toolkit/mozapps/extensions/internal/XPIDatabase.sys.mjs)).
So yes, it persists across restarts, and across Firefox updates, because the
profile survives them.

Note: Mozilla does not publish a sentence that literally says "installs from file
are permanent". The claim rests on the documented Add-ons Manager outcome plus the
fact that it is the same profile-scope install path used by AMO installs.

Installing by navigating to an `https://` URL that serves the XPI also works and
is permanent, but the server must send
`Content-Type: application/x-xpinstall`
([self-distribution, web download](https://extensionworkshop.com/documentation/publish/self-distribution/)).
GitHub Releases assets do not set that header, so a release-asset link is not a
reliable install trigger.

## Q4. Sideloading via profile dir or registry

No longer supported outside ESR.

Firefox 74 release notes: "Add-ons installed by external applications can now be
removed using the Add-ons Manager (about:addons). Going forward, only users can
install add-ons; they cannot be installed by an application."
([Firefox 74 release notes](https://www.mozilla.org/en-US/firefox/74.0/releasenotes/))

Mozilla's developer page confirms and adds the ESR carve-out: "Starting with
Firefox 74, it is no longer possible to have an extension be automatically
installed as part of another application install [...] Enterprise administrators
can do this using policies. Additionally, Firefox Extended Support Release (ESR)
continues to support sideloading as an extension installation method."
([Add-ons for desktop apps](https://extensionworkshop.com/documentation/publish/distribute-for-desktop-apps/),
2020-03-20)

Current build flags match that exactly:

* `toolkit/moz.configure`: `--allow-addon-sideload` has
  `default=milestone.is_esr`, so `MOZ_ALLOW_ADDON_SIDELOAD` is set for ESR builds
  only;
* `AddonSettings.sys.mjs`: without that flag, `SCOPES_SIDELOAD` is a constant equal
  to `SCOPE_PROFILE`, and the pref `extensions.sideloadScopes` is not consulted;
* `firefox.js` sets `extensions.startupScanScopes` to `0` and
  `extensions.autoDisableScopes` to `15` (all scopes), so new files dropped into
  the profile `extensions/` folder are not picked up at startup, and anything that
  does get picked up from a non-user scope starts disabled.

Net: dropping a signed XPI into `<profile>/extensions/` or writing the registry
keys is a dead end on release and beta. It is a documented, supported method only on ESR.

## Q5. Enterprise policy route

**It does not bypass signature checks.** The enterprise doc says all add-ons must
be signed in standard and beta Firefox and recommends either signing the add-on for
self-distribution or deploying ESR for unsigned add-ons
([enterprise distribution](https://extensionworkshop.com/documentation/enterprise/enterprise-distribution/)).
The code agrees: the signature gate in `XPIInstall.sys.mjs` runs before any policy
logic, and policy only ever relaxes weak-algorithm signatures via
`temporarily_allow_weak_signatures` (Fx 127), never the requirement itself.

**Does it need a managed machine?** No. On Windows Firefox reads policies from
`HKEY_CURRENT_USER\SOFTWARE\Policies\Mozilla\<app name>` first, then
`HKEY_LOCAL_MACHINE`, with machine values overriding user values:

```js
// Machine policies override user policies, so we read
// user policies first and then replace them if necessary.
this._readData(wrk, wrk.ROOT_KEY_CURRENT_USER);
this._readData(wrk, wrk.ROOT_KEY_LOCAL_MACHINE);
```

([EnterprisePoliciesParent.sys.mjs](https://searchfox.org/mozilla-central/source/toolkit/components/enterprisepolicies/EnterprisePoliciesParent.sys.mjs))

There is no domain-join check anywhere in that path. HKCU works on a personal PC
and needs no administrator rights, which matters because this app already writes
HKCU keys for native messaging.

`policies.json` is the other route, but on Windows it lives in a `distribution`
folder next to `firefox.exe`
([Configuring policies](https://firefox-admin-docs.mozilla.org/guides/policies-configuration/),
updated 2026-11-06), which is `C:\Program Files\Mozilla Firefox\distribution` for a
normal install and therefore needs admin rights.

**Can `install_url` be a local file?** Yes. Current policy reference, last updated
2026-11-06: "If installing from the local file system, use a `file:///` URL.
Firefox will update or re-install the extension whenever the XPI file at that path
changes."
([ExtensionSettings](https://firefox-admin-docs.mozilla.org/reference/policies/extensionsettings/))

Recent version gates from the same page:

* Fx 151: policy-level `update_url`.
* Fx 152: force-installed extensions update automatically unless
  `updates_disabled` is true.
* Fx 153: `install_url` becomes optional; without it, Firefox installs the latest
  AMO version by ID.
* Fx 155: `DisableLocalPolicies`.
* Fx 158: with `install_url` omitted and `update_url` set, install from that
  update manifest.

Minimal HKCU policy value for this app (REG_SZ `ExtensionSettings` under
`HKEY_CURRENT_USER\SOFTWARE\Policies\Mozilla\Firefox`):

```json
{
  "socialclip@petra-dot": {
    "installation_mode": "force_installed",
    "install_url": "file:///C:/Users/<user>/AppData/.../socialclip-firefox.xpi"
  }
}
```

Practical costs of this route: Firefox then reports "Your browser is being managed
by your organization" in `about:policies`, `force_installed` prevents the user from
removing the add-on, and the whole mechanism depends on a policy surface Mozilla
has been actively editing, including a policy (`DisableLocalPolicies`, Fx 155) that
turns off local policy sources entirely.

## Q6. Developer Edition / Nightly with the pref off

Mozilla explicitly clears the build flag for Developer Edition. From
`browser/config/mozconfigs/linux64/devedition`:

```
# Add-on signing is not required for DevEdition
MOZ_REQUIRE_SIGNING=
```

([mozconfig](https://searchfox.org/mozilla-central/source/browser/config/mozconfigs/linux64/devedition))

So on DevEdition (and on Nightly, whose `a1` version string fails
`is_release_or_beta`) `REQUIRE_SIGNING` falls back to a live pref getter with
default `false` in `AddonSettings`, though `firefox.js` sets the pref default to
`true`, so the user must still flip it in `about:config`.

Survival across updates: yes, the add-on lives in the profile and the profile
survives browser updates. Two caveats from the code:

* if the user later runs release or beta Firefox with the same profile,
  `isUsableAddon()` disables the add-on because `mustSign()` is now true;
* signatures are re-verified about once a day, so an unsigned add-on stays
  "correctly signed" only because the check is skipped entirely on those builds.

Downsides for a normal user: a second browser to install and keep updated, a
hidden `about:config` change, xpinstall UI that looks alarming, no AMO auto-update
(needs `update_url`), and a dependence on Mozilla keeping the DevEdition exemption.
It is a developer workflow, not a distribution channel.

## Q7. Automating signing with web-ext

`web-ext sign` with `--channel unlisted` downloads a signed copy of the extension.
Options ([command reference](https://extensionworkshop.com/documentation/develop/web-ext-command-reference/),
current as of web-ext 10.x):

* `--channel unlisted` is required (since web-ext 8, which also removed
  `--use-submission-api`, `--api-url-prefix`, `--id`).
* `--api-key` / `--api-secret`, JWT issuer and secret from
  addons.mozilla.org, env vars `WEB_EXT_API_KEY` and `WEB_EXT_API_SECRET`.
* `--amo-base-url` defaults to `https://addons.mozilla.org/api/v5/`.
* `--approval-timeout`, default 15 minutes, `0` disables waiting.
* `--artifacts-dir` (global), default `./web-ext-artifacts`.
* `--upload-source-code` only matters if the build is minified or generated.

Sketch:

```bash
npx web-ext sign \
  --source-dir dist/firefox-xpi \
  --channel unlisted \
  --api-key "$WEB_EXT_API_KEY" \
  --api-secret "$WEB_EXT_API_SECRET" \
  --artifacts-dir dist/extension
```

**Does the signature expire?** No expiry is documented, and the signature is over
file contents, so a signed XPI stays installable indefinitely as far as any
Mozilla doc says. What it cannot do is cover *new* code: change one byte and the
manifest hashes no longer match, so every new version needs its own signing run.
Shipping the same signed XPI inside every app release is fine and normal; shipping
an XPI for changed code that was never re-signed is not.

CI notes: the credentials are account-wide and can sign as you. Keep them in
GitHub Actions secrets, never in the repo; this repo already runs gitleaks. The
signing step needs network access and a Node runtime, so it belongs in
`release.yml` after the extension staging step, before the PyInstaller build, so
the signed XPI lands in the bundle.

## Q8. Recent changes that matter (2024 to 2026)

| Date | Version | Change |
|---|---|---|
| 2020-03 | Fx 74 | App-bundled and profile/registry sideloading removed; only users install add-ons ([release notes](https://www.mozilla.org/en-US/firefox/74.0/releasenotes/)) |
| 2024 (date not verified) | Fx 127 | `temporarily_allow_weak_signatures` policy for SHA-1 era signatures |
| 2025-10-14 | Fx 144 | `InstallTrigger` removed (Bug 1776426), per [self-distribution doc](https://extensionworkshop.com/documentation/publish/self-distribution/) |
| 2026-05-19 | Fx 151 | Policy `update_url`; profile-directory add-ons survive profile relocation ([release notes](https://firefox-admin-docs.mozilla.org/release-notes/version/firefox-151/)) |
| 2026-06-16 | Fx 152 | Force-installed extensions auto-update unless `updates_disabled` true |
| 2026-07-21 | Fx 153 | `install_url` optional, `blocked_permissions`, `runtime_blocked_hosts` |
| 2026-09-01 | Fx 155 | `DisableLocalPolicies` (cannot itself be set via policies.json or GPO) |
| 2026-10-13 | Fx 158 | Policy install from `update_url` when `install_url` is omitted |
| 2026-12-01 | n/a | New [Add-on Policies preview](https://extensionworkshop.com/documentation/publish/add-on-policies-preview-2026-12/) takes effect; data-collection disclosure rules tighten |

Nothing in that list changes the recommendation. The trend is the opposite of
loosening: sideloading is gone, signature enforcement is compile-time, and the
policy surface keeps shifting.

## Recommended path for SocialClip

**Ship a signed unlisted XPI and install it from file. Keep enterprise policy as an
optional power-user switch, not the default.**

Why this one: free, no store listing, permission-free, survives restarts and
Firefox upgrades, needs no admin, no domain, no second browser, and it is the only
route Mozilla documents as a first-class self-distribution channel today.

### Maintainer setup (once)

1. Create a free account on addons.mozilla.org, then generate API credentials
   (JWT issuer and secret) from the developer hub.
2. Store them as repository secrets `WEB_EXT_API_KEY` and `WEB_EXT_API_SECRET`.
3. Note the add-on ID `socialclip@petra-dot`: it is already in
   `extension/manifest.firefox.json` and must match
   `core/native_install.py:FIREFOX_ADDON_ID`. AMO will bind the signature
   certificate to it.

### Build and signing step (per release)

The current `extension/` folder cannot be zipped as-is: `manifest.json` is the
Chromium manifest (`service_worker` plus a Chrome `key`), and Firefox needs the
Firefox manifest at the archive root under the name `manifest.json`.

```bash
mkdir -p dist/firefox-xpi
cp -r extension/* dist/firefox-xpi/
cp extension/manifest.firefox.json dist/firefox-xpi/manifest.json
rm dist/firefox-xpi/manifest.firefox.json
npx web-ext sign --source-dir dist/firefox-xpi --channel unlisted \
  --api-key "$WEB_EXT_API_KEY" --api-secret "$WEB_EXT_API_SECRET" \
  --artifacts-dir dist/extension
```

Result: `dist/extension/socialclip_downloader-<version>.xpi`, signed.

Optionally `npx web-ext lint --source-dir dist/firefox-xpi` first; it catches the
kind of manifest error that turns into an AMO rejection.

### Packaging change

`release.yml` builds with
`--add-data extension:extension` ([release.yml](../../.github/workflows/release.yml)).
Add the signed XPI to the same data mapping (for example
`--add-data dist/extension/socialclip_downloader-x.y.z.xpi:extension`) so
`core/extension.py:source_dir()` can find it from `sys._MEIPASS`.

### App change

`ui/main_window.py` currently prints the `about:debugging` / Load Temporary Add-on
text. Replace it with:

* a **Firefox** section that calls `core.extension.source_dir()` to locate the
  bundled `.xpi` and opens it with the OS handler (`QDesktopServices.openUrl` on
  `QUrl.fromLocalFile`) or `os.startfile` on Windows;
* a fallback line of text: "If nothing happens: open `about:addons`, click the cog,
  choose Install Add-on From File, and pick `<path>`";
* a **Copy path** button, since that fallback is the documented flow.

`core/native_install.py` needs no change: it already writes
`Software\Mozilla\NativeMessagingHosts\<host>` in HKCU with `allowed_extensions`
set to `socialclip@petra-dot`, which is exactly the Firefox shape
([MDN native manifests](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Native_manifests)).

### Versioning

Firefox treats add-on versions per manifest, not per app version. Two options:

* **Simplest:** bump `extension/manifest.firefox.json` and `manifest.json` version
  together with the app release. Users who want the new extension code reinstall
  from the new app build. No infrastructure.
* **Nicer:** add `browser_specific_settings.gecko.update_url` pointing at an
  `updates.json` hosted on the release page or a static site, then Firefox updates
  installed copies on its own. This needs an HTTPS host and a correctly signed
  `updates.json`, so only do it when extension churn justifies it.

### Optional: zero-click via HKCU policy

Worth offering behind an explicit checkbox ("install for all Firefox profiles on
this PC"), not as the default:

* requires the same signed XPI, so it is additive to the work above;
* writes one REG_SZ `ExtensionSettings` value under
  `HKCU\Software\Policies\Mozilla\Firefox`, no admin needed;
* `install_url` must be `file:///` with the XPI path (documented), and Firefox
  re-installs when the file's internal version changes;
* the user will see "managed by your organization" in `about:policies`, which is
  confusing for a personal download and a support burden;
* depends on a policy surface under active churn (`DisableLocalPolicies`, Fx 155).

Do not ship this as the only path.

### What not to do

* Do not tell users to set `xpinstall.signatures.required=false` on release
  Firefox. It is inert there.
* Do not ship an unsigned XPI "because Chrome allows developer mode". Chrome's
  unpacked load has no Firefox equivalent that persists.
* Do not drop the XPI into the profile `extensions/` folder. Not scanned on
  release builds.

## Unverified / version-dependent

These are the points I could not close with a primary source, or that depend on
build details that can change without a doc update:

1. **Literal "permanent" wording for install-from-file.** No Mozilla doc says the
   word. Support is the documented Add-ons Manager outcome plus the profile-scope
   install path in the source. High confidence, but it is inference.
2. **Drag-and-drop an XPI onto the Firefox window.** Historically worked, is not
   documented today, and I did not test it. Treat the cog menu as the only
   supported flow; opening the local `.xpi` (double-click) is the likely one-click
   equivalent and should be verified on Windows before shipping UI that relies on
   it.
3. **Signature certificate validity period.** No Mozilla doc states an expiry for
   AMO signatures, and I found no statement that Firefox ignores certificate
   expiry dates at install time. Practical mitigation: re-sign every release, so
   any expiry question only affects users who never update.
4. **AMO "free" wording.** No doc says "free"; equally, none mentions a fee, and
   account creation asks for no payment method. Treated as free.
5. **Manual review queue times for unlisted submissions.** The only documented
   figure is the 24-hour worst case in the signing overview. Real times vary.
6. **`DisableLocalPolicies` trigger channel (Fx 155).** The reference says it
   cannot be applied via policies.json, GPO, or macOS plist, which implies some
   other delivery path. What that path is, and whether it could ever be flipped on
   by default, is unclear. Monitor.
7. **Policy precedence details.** If both HKCU/HKLM policies and a
   `distribution/policies.json` exist, the exact merge rules are not documented on
   the current reference page. Avoid combining them.
8. **Bug 1776426 (`InstallTrigger` removal).** Cited by the self-distribution page;
   the Bugzilla entry itself was not readable during this research (Bugzilla REST
   returned 400, HTML blocked). The removal date and version come from Mozilla's
   own doc, not from the bug.
9. **Firefox for Android.** Out of scope here; Android install-from-file requires
   the hidden menu in Settings and is documented separately.
