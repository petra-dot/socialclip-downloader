const HOST = "com.petra_dot.socialclip";
const api = globalThis.browser ?? globalThis.chrome;
const store = api.storage.session || api.storage.local;

const $ = (id) => document.getElementById(id);
const FALLBACK = {
  outputs: ["MP4", "MP3"],
  resolutions: ["720", "1080", "1440", "2160"],
};

let known = { in_queue: [], in_history: [] };
let rows = [];

async function host(message) {
  return api.runtime.sendNativeMessage(HOST, message);
}

function normalize(url) {
  try {
    const parsed = new URL(url);
    if (!/^https?:$/.test(parsed.protocol)) return "";
    parsed.search = "";
    parsed.hash = "";
    return parsed.href.replace(/\/$/, "");
  } catch (error) {
    return "";
  }
}

function hostnameOf(url) {
  try {
    return new URL(url).hostname.toLowerCase();
  } catch (error) {
    return "";
  }
}

function supported(hostname, sites) {
  return sites.some((site) => {
    try {
      return new RegExp("^(?:" + site.pattern + ")$").test(hostname);
    } catch (error) {
      return false;
    }
  });
}

function setStatus(text) {
  $("status").textContent = text;
}

async function sitesList() {
  const cached = (await api.storage.local.get("sites")).sites;
  if (cached && cached.length) return cached;
  try {
    const reply = await host({ cmd: "sites" });
    const sites = (reply && reply.sites) || [];
    if (sites.length) await api.storage.local.set({ sites });
    return sites;
  } catch (error) {
    return cached || [];
  }
}

async function refreshFormats() {
  let formats;
  try {
    const reply = await host({ cmd: "formats" });
    if (!reply || !reply.ok) throw new Error("bad reply");
    formats = reply;
    await api.storage.local.set({ formats });
  } catch (error) {
    formats = (await api.storage.local.get("formats")).formats || FALLBACK;
    setStatus("App not reachable. Start SocialClip Downloader once, then retry.");
  }
  fill("output", formats.outputs);
  fill("resolution", formats.resolutions);
  const saved = (await api.storage.local.get("choice")).choice;
  if (saved) {
    if (formats.outputs.includes(saved.output)) $("output").value = saved.output;
    if (formats.resolutions.includes(saved.resolution)) {
      $("resolution").value = saved.resolution;
    }
  }
  syncResolution();
}

function fill(id, values) {
  const select = $(id);
  select.innerHTML = "";
  for (const value of values) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  }
}

function syncResolution() {
  $("resolution").disabled = $("output").value === "MP3";
}

async function currentChoice() {
  const choice = { output: $("output").value, resolution: $("resolution").value };
  await api.storage.local.set({ choice });
  return choice;
}

async function knownFor(urls) {
  try {
    known = await host({ cmd: "check", urls });
  } catch (error) {
    known = { in_queue: [], in_history: [] };
  }
  const keys = (list) => new Set((list || []).map(normalize));
  return { queue: keys(known.in_queue), history: keys(known.in_history) };
}

function render() {
  const list = $("links");
  list.innerHTML = "";
  list.hidden = rows.length === 0;
  for (const row of rows) {
    const item = document.createElement("li");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = row.checked;
    box.dataset.url = row.url;
    box.addEventListener("change", () => {
      row.checked = box.checked;
      updateWarning();
    });
    const label = document.createElement("span");
    label.className = "url";
    label.textContent = row.url;
    label.title = row.url;
    item.append(box, label);
    if (row.chip) {
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.textContent = row.chip;
      item.appendChild(chip);
    }
    list.appendChild(item);
  }
  updateWarning();
}

function updateWarning() {
  const selected = checkedUrls();
  const flagged = rows.filter((row) => row.checked && row.chip);
  const warning = $("warning");
  if (flagged.length) {
    const queued = flagged.filter((row) => row.chip === "in queue").length;
    const done = flagged.length - queued;
    const parts = [];
    if (queued) parts.push(queued + " already in the queue");
    if (done) parts.push(done + " already downloaded");
    warning.textContent = "This is " + parts.join(" and ") + ". Add anyway?";
    warning.hidden = false;
    $("add").textContent = "Add anyway";
    $("now").textContent = "Download anyway";
  } else {
    warning.hidden = true;
    $("add").textContent = "Add to queue";
    $("now").textContent = "Download now";
  }
  const any = selected.length > 0;
  $("add").disabled = !any;
  $("now").disabled = !any;
}

function checkedUrls() {
  return rows.filter((row) => row.checked).map((row) => row.url);
}

async function loadPending() {
  const pending = (await store.get("pending")).pending;
  if (!pending) return;
  await store.remove("pending");
  const keys = await knownFor(pending.urls);
  rows = pending.urls.map((url) => ({
    url,
    checked: true,
    chip: keys.queue.has(normalize(url)) ? "in queue" : "already downloaded",
  }));
  render();
  setStatus(pending.reason === "queue"
    ? "Already in your queue."
    : "Already in your history.");
}

async function scanPage() {
  setStatus("Scanning...");
  const sites = await sitesList();
  if (!sites.length) {
    setStatus("No site list yet. Open the app once so the extension can cache it.");
    return;
  }
  let hrefs = [];
  try {
    const [tab] = await api.tabs.query({ active: true, currentWindow: true });
    const results = await api.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => Array.from(document.links, (a) => a.href),
    });
    hrefs = (results[0] && results[0].result) || [];
  } catch (error) {
    setStatus("This page cannot be scanned.");
    return;
  }
  const seen = new Set();
  const found = [];
  for (const raw of hrefs) {
    const hostname = hostnameOf(raw);
    if (!hostname || !supported(hostname, sites)) continue;
    const key = normalize(raw);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    found.push(raw);
    if (found.length >= 200) break;
  }
  if (!found.length) {
    setStatus("No supported links on this page.");
    rows = [];
    render();
    return;
  }
  const keys = await knownFor(found);
  rows = found.map((url) => {
    const key = normalize(url);
    return {
      url,
      checked: !keys.queue.has(key),
      chip: keys.queue.has(key) ? "in queue"
        : keys.history.has(key) ? "already downloaded" : "",
    };
  });
  render();
  setStatus(found.length + " supported link(s). Pick what you want.");
}

async function addThisTab() {
  let url = "";
  try {
    const [tab] = await api.tabs.query({ active: true, currentWindow: true });
    const results = await api.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => location.href,
    });
    url = (results[0] && results[0].result) || "";
  } catch (error) {
    setStatus("This page cannot be read.");
    return;
  }
  if (!url) {
    setStatus("No URL for this tab.");
    return;
  }
  const keys = await knownFor([url]);
  const key = normalize(url);
  rows = [{
    url,
    checked: true,
    chip: keys.queue.has(key) ? "in queue"
      : keys.history.has(key) ? "already downloaded" : "",
  }];
  render();
  setStatus("Ready.");
}

async function submit(start) {
  const urls = checkedUrls();
  if (!urls.length) return;
  const choice = await currentChoice();
  $("add").disabled = true;
  $("now").disabled = true;
  try {
    const reply = await host({
      cmd: "add", urls, start,
      output: choice.output, resolution: choice.resolution,
    });
    if (!reply || !reply.ok) throw new Error((reply && reply.error) || "failed");
    setStatus("Added " + reply.added + " to SocialClip.");
    setTimeout(() => window.close(), 800);
  } catch (error) {
    setStatus("Could not reach the app: " + error.message);
    $("add").disabled = false;
    $("now").disabled = false;
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  $("output").addEventListener("change", syncResolution);
  $("scan").addEventListener("click", scanPage);
  $("add-tab").addEventListener("click", addThisTab);
  $("add").addEventListener("click", () => submit(false));
  $("now").addEventListener("click", () => submit(true));
  await refreshFormats();
  await loadPending();
  if (!rows.length) updateWarning();
});
