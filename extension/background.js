// Context menus and the host calls they make. The popup owns everything a
// user has to choose; this file only decides between "just add" and
// "ask first because it is already known".
const HOST = "com.petra_dot.socialclip";
const api = globalThis.browser ?? globalThis.chrome;
const store = api.storage.session || api.storage.local;

const MENUS = [
  { id: "add", title: "Add to SocialClip Queue" },
  { id: "now", title: "Download now with SocialClip" },
];

const ACCENT = "#0d7d75";

// A context-menu add has no window to report into, so the toolbar says so.
async function flashBadge(count) {
  try {
    await api.action.setBadgeBackgroundColor({ color: ACCENT });
    await api.action.setBadgeText({ text: String(count) });
    await api.action.setTitle({ title: "Added to the SocialClip queue" });
    setTimeout(() => {
      api.action.setBadgeText({ text: "" });
      api.action.setTitle({ title: "SocialClip" });
    }, 4000);
  } catch (error) {
    // The badge is a nicety; never fail the add over it.
  }
}

api.runtime.onInstalled.addListener(() => {
  for (const menu of MENUS) {
    api.contextMenus.create({
      id: menu.id,
      title: menu.title,
      contexts: ["link", "video", "audio", "page"],
    });
  }
});

async function host(message) {
  return api.runtime.sendNativeMessage(HOST, message);
}

async function choice() {
  const saved = (await api.storage.local.get("choice")).choice;
  return saved || { output: "MP4", resolution: "1080" };
}

async function openPopup() {
  try {
    await api.action.openPopup();
    return true;
  } catch (error) {
    return false;
  }
}

async function warn() {
  await api.action.setBadgeText({ text: "!" });
  await api.action.setTitle({ title: "SocialClip: app not reachable" });
}

api.contextMenus.onClicked.addListener(async (info, tab) => {
  const url = info.linkUrl || info.srcUrl || info.pageUrl || (tab && tab.url);
  if (!url) return;
  const start = info.menuItemId === "now";
  await api.action.setBadgeText({ text: "" });
  try {
    const found = await host({ cmd: "check", urls: [url] });
    const reason = (found.in_queue || []).length ? "queue"
      : (found.in_history || []).length ? "history" : "";
    // Download now always asks for the format first. Add to queue stays a
    // one-click action unless the link is already known.
    if (start || reason) {
      await store.set({ pending: { urls: [url], start, reason } });
      if (!(await openPopup())) {
        await api.action.setTitle({ title: "SocialClip: click to confirm" });
        await api.action.setBadgeText({ text: "!" });
      }
      return;
    }
    const pick = await choice();
    const reply = await host({ cmd: "add", urls: [url], start: false, ...pick });
    if (reply && reply.ok) await flashBadge(reply.added || 1);
  } catch (error) {
    await warn();
  }
});
