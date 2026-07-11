const { app, BrowserWindow, ipcMain, screen, Menu, Tray, shell } = require("electron");
const fs = require("fs");
const path = require("path");
const http = require("http");

let win = null;
let settingsWin = null;
let tray = null;
let geometryFile = "";
let lastState = null;
let syncTimer = null;
let cursorTimer = null;
let talkTimer = null;
let writeTimer = null;
let isDragging = false;
let isDocked = false;
let dragOffset = { x: 0, y: 0 };
let dockDragOffset = { x: 0, y: 0 };
let dockDragStart = { x: 0, y: 0 };
let mousePassthrough = false;
let dockMouseCaptured = false;
let hoverState = { active: false, chat: "" };
let chatHistory = [];
let chatBusy = false;
let seenMessageIds = new Set();
let nextAutoTalkAt = 0;

const WEB_URL = "http://127.0.0.1:59137";
const AUTO_PET_TALK_MIN_SECONDS = 45;
const AUTO_PET_TALK_MAX_SECONDS = 110;
const BASE_WIDTH = 250;
const BASE_HEIGHT = 350;
const PET_SIZE_PRESETS = [75, 100, 125, 150, 200];
const EDGE_DOCK_THRESHOLD = 28;
const EDGE_UNDOCK_DRAG_THRESHOLD = 42;
const EDGE_STRIP_THICKNESS = 12;
const EDGE_STRIP_LENGTH = 170;
const EDGE_HINT_SPACE = 250;
const I18N = {
  "zh-CN": {
    appName: "AI陪伴桌宠",
    showPet: "显示伙伴",
    hidePet: "隐藏伙伴",
    closePet: "关闭桌宠",
    chat: "对话",
    realtime: "实时对话",
    talkToPets: "和其他桌宠说话",
    openWeb: "打开网页",
    openLive2D: "打开 Live2D",
    refresh: "刷新显示",
    edgeHide: "贴边隐藏",
    edgeShow: "取消贴边隐藏",
    alwaysOnTop: "置顶",
    launchAtLogin: "开机自启",
    size: "大小",
    settings: "设置",
    openSettings: "打开设置",
    quit: "终止程序",
    settingsTitle: "AI陪伴桌宠设置",
    onlyMe: "现在只有我一个桌宠在线。",
    otherPet: "另一个桌宠",
    live2dPet: "Live2D 桌宠",
    model3dPet: "3D 桌宠",
  },
  "en-US": {
    appName: "AI Companion Pet",
    showPet: "Show Companion",
    hidePet: "Hide Companion",
    closePet: "Close Pet",
    chat: "Chat",
    realtime: "Realtime Chat",
    talkToPets: "Talk to Other Pets",
    openWeb: "Open Console",
    openLive2D: "Open Live2D",
    refresh: "Refresh",
    edgeHide: "Dock to Edge",
    edgeShow: "Undock from Edge",
    alwaysOnTop: "Always on Top",
    launchAtLogin: "Launch at Login",
    size: "Size",
    settings: "Settings",
    openSettings: "Open Settings",
    quit: "Quit App",
    settingsTitle: "AI Companion Pet Settings",
    onlyMe: "I am the only companion online right now.",
    otherPet: "Another companion",
    live2dPet: "Live2D Pet",
    model3dPet: "3D Pet",
  }
};

function currentLocale() {
  const candidates = [];
  if (geometryFile) candidates.push(path.join(path.dirname(geometryFile), "..", "app_config.json"));
  candidates.push(path.join(__dirname, "..", "data", "app_config.json"));
  for (const candidate of candidates) {
    try {
      const data = JSON.parse(fs.readFileSync(path.resolve(candidate), "utf8"));
      const raw = String(data.locale || "").toLowerCase();
      if (raw === "en" || raw === "en-us") return "en-US";
      if (raw === "zh" || raw === "zh-cn" || raw === "zh-hans") return "zh-CN";
    } catch (_error) {
    }
  }
  return "zh-CN";
}

function t(key) {
  const locale = currentLocale();
  return (I18N[locale] && I18N[locale][key]) || I18N["zh-CN"][key] || key;
}

function iconPath() {
  const candidates = [
    path.join(__dirname, "..", "pet_icon.ico"),
    path.join(__dirname, "..", "ai_icon.ico")
  ];
  return candidates.find((candidate) => fs.existsSync(candidate)) || "";
}

function argValue(name, fallback = "") {
  const index = process.argv.indexOf(name);
  if (index >= 0 && index + 1 < process.argv.length) return process.argv[index + 1];
  return fallback;
}

function readState() {
  try {
    const text = fs.readFileSync(geometryFile, "utf8");
    return normalizeState(JSON.parse(text));
  } catch (_error) {
    return normalizeState(lastState || {
      ...defaultBounds(),
      visible: true,
      closed: false,
      url: WEB_URL + "/live2d?pet=1&shell=1"
    });
  }
}

function normalizeState(state) {
  return {
    ...state,
    always_on_top: state && typeof state.always_on_top === "boolean" ? state.always_on_top : true,
    docked: Boolean(state && state.docked),
    dock_edge: state && state.dock_edge ? String(state.dock_edge) : "",
    launch_at_login: isStartupEnabled()
  };
}

function runtimeDir() {
  if (geometryFile) return path.dirname(geometryFile);
  return path.join(__dirname, "..", "data", "runtime");
}

function appRootDir() {
  return path.resolve(__dirname, "..");
}

function talkFile() {
  return path.join(runtimeDir(), "pet_talk.json");
}

function startupFolder() {
  const appdata = process.env.APPDATA || path.join(process.env.USERPROFILE || "", "AppData", "Roaming");
  return path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup");
}

function startupCmdPath() {
  return path.join(startupFolder(), "CompanionAI-Routine.cmd");
}

function isStartupEnabled() {
  try {
    return fs.existsSync(startupCmdPath());
  } catch (_error) {
    return false;
  }
}

function setStartupEnabled(enabled) {
  const startupPath = startupCmdPath();
  try {
    if (enabled) {
      const root = appRootDir();
      const launcherAi = path.join(root, "Launch Companion AI.ps1");
      const launcherPet = path.join(root, "Launch Companion Pet.ps1");
      const lines = [
        "@echo off",
        `cd /d "${root}"`,
        `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "${launcherAi}"`,
        `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "${launcherPet}"`
      ];
      fs.mkdirSync(path.dirname(startupPath), { recursive: true });
      fs.writeFileSync(startupPath, lines.join("\r\n") + "\r\n", "utf8");
    } else if (fs.existsSync(startupPath)) {
      fs.unlinkSync(startupPath);
    }
  } catch (_error) {
  }
}

function instanceId() {
  return `electron-${process.pid}`;
}

function companionName() {
  const style = argValue("--style", "live2d");
  return `${style === "3d" ? t("model3dPet") : t("live2dPet")} ${String(process.pid).slice(-4)}`;
}

function safeReadTalkBus() {
  try {
    const data = JSON.parse(fs.readFileSync(talkFile(), "utf8"));
    if (data && typeof data === "object") return data;
  } catch (_error) {
  }
  return { companions: [], messages: [] };
}

function safeWriteTalkBus(data) {
  try {
    fs.mkdirSync(path.dirname(talkFile()), { recursive: true });
    const tmp = talkFile() + ".tmp";
    fs.writeFileSync(tmp, JSON.stringify(data), "utf8");
    fs.renameSync(tmp, talkFile());
  } catch (_error) {
  }
}

function pruneTalkBus(data) {
  const now = Date.now() / 1000;
  const companions = (data.companions || []).filter((item) => {
    return now - Number(item.updated_at || 0) < 30;
  });
  const messages = (data.messages || []).filter((item) => {
    return now - Number(item.created_at || 0) < 180;
  }).slice(-80);
  return { companions, messages };
}

function syncHeartbeat() {
  const style = argValue("--style", "live2d");
  const now = Date.now() / 1000;
  const data = pruneTalkBus(safeReadTalkBus());
  const mine = {
    id: instanceId(),
    name: companionName(),
    style,
    updated_at: now
  };
  data.companions = [
    mine,
    ...(data.companions || []).filter((item) => item.id !== mine.id)
  ];
  safeWriteTalkBus(data);
}

function appendPetMessage(text, kind = "talk", replyTo = "") {
  const data = pruneTalkBus(safeReadTalkBus());
  const message = {
    id: `${process.pid}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    from_id: instanceId(),
    from_name: companionName(),
    text: String(text || "").trim(),
    kind,
    reply_to: replyTo,
    created_at: Date.now() / 1000
  };
  if (message.text) data.messages.push(message);
  safeWriteTalkBus(data);
  seenMessageIds.add(message.id);
  return message;
}

function cleanShortPetText(text, limit = 34) {
  let value = String(text || "").trim().replace(/\s+/g, " ");
  for (const prefix of ["AI:", "我：", "桌宠：", "助手："]) {
    if (value.startsWith(prefix)) value = value.slice(prefix.length).trim();
  }
  if (value.includes("\n")) value = value.split(/\r?\n/)[0].trim();
  if (value.length > limit) value = value.slice(0, limit - 1) + "…";
  return value;
}

async function makePetReply(sender, text) {
  const prompt = [
    "你是一个桌面宠物，正在和另一个桌宠聊天。",
    "请用一句自然、可爱但不过分夸张的中文回复。",
    "只输出一句话，不要超过24个字。",
    `对方名字：${sender}`,
    `对方说：${text}`
  ].join("\n");
  const reply = await fetchChatReply(prompt);
  return cleanShortPetText(reply) || "我听见啦，我们一起陪着用户。";
}

async function startPetConversation() {
  syncHeartbeat();
  const data = pruneTalkBus(safeReadTalkBus());
  const peers = (data.companions || []).filter((item) => item.id !== instanceId());
  if (peers.length <= 0) {
    showPetMessage(t("onlyMe"));
    return;
  }
  const prompt = "你是一个桌面宠物，现在想主动和另一个桌宠说一句话。请用一句自然、轻松、不会打扰用户的中文开场。只输出一句话，不要超过24个字。";
  const text = cleanShortPetText(await fetchChatReply(prompt)) || "你也在呀，一起安静陪着吧。";
  appendPetMessage(text, "talk");
  showPetMessage(text);
  scheduleNextAutoTalk();
}

function showPetMessage(text) {
  if (!win || win.isDestroyed()) return;
  win.webContents.send("pet-action", {
    action: "show-message",
    text: cleanShortPetText(text, 80),
    docked: isDocked
  });
}

function scheduleNextAutoTalk() {
  const seconds = AUTO_PET_TALK_MIN_SECONDS + Math.random() * (AUTO_PET_TALK_MAX_SECONDS - AUTO_PET_TALK_MIN_SECONDS);
  nextAutoTalkAt = Date.now() + seconds * 1000;
}

function startTalkLoop() {
  scheduleNextAutoTalk();
  if (talkTimer) clearInterval(talkTimer);
  talkTimer = setInterval(async () => {
    syncHeartbeat();
    const data = pruneTalkBus(safeReadTalkBus());
    for (const message of data.messages || []) {
      if (!message.id || seenMessageIds.has(message.id)) continue;
      seenMessageIds.add(message.id);
      if (message.from_id === instanceId()) continue;
      const sender = message.from_name || t("otherPet");
      const text = String(message.text || "").trim();
      if (!text) continue;
      showPetMessage(`${sender}：${text}`);
      if (message.kind === "talk") {
        const reply = await makePetReply(sender, text);
        appendPetMessage(reply, "reply", message.id);
        showPetMessage(reply);
      }
    }
    const peers = (data.companions || []).filter((item) => item.id !== instanceId());
    if (peers.length > 0 && Date.now() >= nextAutoTalkAt && !chatBusy && !hoverState.active && Math.random() <= 0.45) {
      await startPetConversation();
    } else if (Date.now() >= nextAutoTalkAt) {
      scheduleNextAutoTalk();
    }
  }, 1200);
}

function writeState(partial) {
  try {
    const current = readState();
    const next = { ...current, ...partial, updated_at: Date.now() / 1000 };
    const tmp = geometryFile + ".tmp";
    fs.writeFileSync(tmp, JSON.stringify(next), "utf8");
    fs.renameSync(tmp, geometryFile);
    lastState = next;
  } catch (_error) {
  }
}

function scheduleWrite(partial) {
  if (writeTimer) clearTimeout(writeTimer);
  writeTimer = setTimeout(() => {
    writeTimer = null;
    writeState(partial);
  }, 50);
}

function cancelScheduledWrite() {
  if (!writeTimer) return;
  clearTimeout(writeTimer);
  writeTimer = null;
}

function persistCurrentWindowBounds(partial = {}) {
  if (!win || win.isDestroyed()) return;
  cancelScheduledWrite();
  const bounds = win.getBounds();
  writeState({
    x: bounds.x,
    y: bounds.y,
    w: bounds.width,
    h: bounds.height,
    electron_moved: true,
    ...partial
  });
}

function defaultBounds() {
  try {
    const display = screen.getPrimaryDisplay();
    const area = display.workArea;
    return {
      x: area.x + area.width - 400,
      y: area.y + area.height - 400,
      w: 250,
      h: 350
    };
  } catch (_error) {
    return { x: 500, y: 300, w: 250, h: 350 };
  }
}

function expandedBoundsFromState(state) {
  return {
    x: Number.isFinite(Number(state.x)) ? Math.round(Number(state.x)) : 500,
    y: Number.isFinite(Number(state.y)) ? Math.round(Number(state.y)) : 300,
    width: Math.max(120, Math.round(Number(state.w) || 180)),
    height: Math.max(160, Math.round(Number(state.h) || 220))
  };
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function displayAreaForBounds(bounds) {
  try {
    return screen.getDisplayMatching(bounds).workArea;
  } catch (_error) {
    return screen.getPrimaryDisplay().workArea;
  }
}

function collapsedBoundsFor(edge, expandedBounds) {
  const area = displayAreaForBounds(expandedBounds);
  const centerX = expandedBounds.x + expandedBounds.width / 2;
  const centerY = expandedBounds.y + expandedBounds.height / 2;
  const verticalHeight = Math.round(clamp(expandedBounds.height * 0.48, EDGE_STRIP_LENGTH, 230));
  const horizontalWidth = Math.round(clamp(expandedBounds.width * 0.72, EDGE_STRIP_LENGTH, 270));

  if (edge === "left") {
    const height = Math.min(verticalHeight, area.height);
    return {
      x: area.x,
      y: Math.round(clamp(centerY - height / 2, area.y, area.y + area.height - height)),
      width: EDGE_HINT_SPACE + EDGE_STRIP_THICKNESS,
      height
    };
  }
  if (edge === "right") {
    const height = Math.min(verticalHeight, area.height);
    const width = EDGE_HINT_SPACE + EDGE_STRIP_THICKNESS;
    return {
      x: area.x + area.width - width,
      y: Math.round(clamp(centerY - height / 2, area.y, area.y + area.height - height)),
      width,
      height
    };
  }
  if (edge === "top") {
    const width = Math.min(horizontalWidth, area.width);
    return {
      x: Math.round(clamp(centerX - width / 2, area.x, area.x + area.width - width)),
      y: area.y,
      width,
      height: EDGE_HINT_SPACE + EDGE_STRIP_THICKNESS
    };
  }

  const width = Math.min(horizontalWidth, area.width);
  const height = EDGE_HINT_SPACE + EDGE_STRIP_THICKNESS;
  return {
    x: Math.round(clamp(centerX - width / 2, area.x, area.x + area.width - width)),
    y: area.y + area.height - height,
    width,
    height
  };
}

function detectDockEdge(bounds) {
  const area = displayAreaForBounds(bounds);
  const areaRight = area.x + area.width;
  const areaBottom = area.y + area.height;
  const boundsRight = bounds.x + bounds.width;
  const boundsBottom = bounds.y + bounds.height;
  const distances = [
    { edge: "left", value: bounds.x - area.x },
    { edge: "right", value: areaRight - boundsRight },
    { edge: "top", value: bounds.y - area.y },
    { edge: "bottom", value: areaBottom - boundsBottom }
  ].filter((item) => item.value <= EDGE_DOCK_THRESHOLD).sort((a, b) => {
    const aPastEdge = a.value < 0;
    const bPastEdge = b.value < 0;
    if (aPastEdge !== bPastEdge) return aPastEdge ? -1 : 1;
    if (aPastEdge && bPastEdge) return a.value - b.value;
    return a.value - b.value;
  });
  return distances.length ? distances[0].edge : "";
}

function nearestDockEdge(bounds) {
  const area = displayAreaForBounds(bounds);
  const areaRight = area.x + area.width;
  const areaBottom = area.y + area.height;
  const boundsRight = bounds.x + bounds.width;
  const boundsBottom = bounds.y + bounds.height;
  const distances = [
    { edge: "left", value: Math.abs(bounds.x - area.x) },
    { edge: "right", value: Math.abs(areaRight - boundsRight) },
    { edge: "top", value: Math.abs(bounds.y - area.y) },
    { edge: "bottom", value: Math.abs(areaBottom - boundsBottom) }
  ].sort((a, b) => a.value - b.value);
  return distances.length ? distances[0].edge : "right";
}

function toggleEdgeDock() {
  if (!win || win.isDestroyed()) return;
  if (isDocked) {
    undockPetWindow();
    return;
  }
  dockPetWindow(nearestDockEdge(win.getBounds()));
}

function sendDockState(edge = "") {
  if (!win || win.isDestroyed()) return;
  win.webContents.send("pet-action", {
    action: "dock-state",
    docked: isDocked,
    edge: edge || ""
  });
}

function setWindowMousePassthrough(active) {
  if (!win || win.isDestroyed()) return;
  const next = Boolean(active);
  if (mousePassthrough === next) return;
  mousePassthrough = next;
  win.setIgnoreMouseEvents(next, { forward: true });
}

function moveDockedWindow(screenX, screenY) {
  if (!win || win.isDestroyed() || !isDocked) return;
  const state = readState();
  const edge = state.dock_edge || "";
  if (!edge) return;
  const bounds = win.getBounds();
  const area = displayAreaForBounds(bounds);
  const dragOutDistance = {
    left: screenX - dockDragStart.x,
    right: dockDragStart.x - screenX,
    top: screenY - dockDragStart.y,
    bottom: dockDragStart.y - screenY
  }[edge] || 0;

  if (dragOutDistance >= EDGE_UNDOCK_DRAG_THRESHOLD) {
    const expanded = expandedBoundsFromState(state);
    isDocked = false;
    dockMouseCaptured = false;
    setWindowMousePassthrough(false);
    dragOffset = {
      x: Math.round(clamp(dockDragOffset.x, 0, expanded.width)),
      y: Math.round(clamp(dockDragOffset.y, 0, expanded.height))
    };
    const nextX = Math.round(screenX - dragOffset.x);
    const nextY = Math.round(screenY - dragOffset.y);
    win.setBounds({
      x: nextX,
      y: nextY,
      width: expanded.width,
      height: expanded.height
    }, false);
    writeState({
      x: nextX,
      y: nextY,
      w: expanded.width,
      h: expanded.height,
      docked: false,
      dock_edge: "",
      visible: true,
      closed: false,
      electron_moved: true
    });
    sendDockState("");
    return;
  }

  if (edge === "left" || edge === "right") {
    const x = edge === "left" ? area.x : area.x + area.width - bounds.width;
    const y = Math.round(clamp(screenY - dockDragOffset.y, area.y, area.y + area.height - bounds.height));
    win.setBounds({ x, y, width: bounds.width, height: bounds.height }, false);
    return;
  }

  const x = Math.round(clamp(screenX - dockDragOffset.x, area.x, area.x + area.width - bounds.width));
  const y = edge === "top" ? area.y : area.y + area.height - bounds.height;
  win.setBounds({ x, y, width: bounds.width, height: bounds.height }, false);
}

function persistDockedWindowPosition() {
  if (!win || win.isDestroyed() || !isDocked) return;
  const state = readState();
  const edge = state.dock_edge || "";
  if (!edge) return;
  const expanded = expandedBoundsFromState(state);
  const collapsed = win.getBounds();
  const next = { electron_moved: true };

  if (edge === "left" || edge === "right") {
    next.y = Math.round(collapsed.y + collapsed.height / 2 - expanded.height / 2);
  } else {
    next.x = Math.round(collapsed.x + collapsed.width / 2 - expanded.width / 2);
  }

  writeState(next);
}

function dockPetWindow(edge) {
  if (!win || win.isDestroyed() || !edge) return;
  const expanded = win.getBounds();
  const collapsed = collapsedBoundsFor(edge, expanded);
  isDocked = true;
  dockMouseCaptured = false;
  win.setBounds(collapsed, false);
  setWindowMousePassthrough(true);
  writeState({
    x: expanded.x,
    y: expanded.y,
    w: expanded.width,
    h: expanded.height,
    docked: true,
    dock_edge: edge,
    electron_moved: true
  });
  sendDockState(edge);
}

function undockPetWindow() {
  if (!win || win.isDestroyed()) return;
  const expanded = expandedBoundsFromState(readState());
  isDocked = false;
  dockMouseCaptured = false;
  setWindowMousePassthrough(false);
  win.setBounds(expanded, false);
  if (!win.isVisible()) win.showInactive();
  writeState({
    x: expanded.x,
    y: expanded.y,
    w: expanded.width,
    h: expanded.height,
    docked: false,
    dock_edge: "",
    visible: true,
    closed: false,
    electron_moved: true
  });
  sendDockState("");
  scheduleViewerRefresh();
}

function applyState(state) {
  if (!win || win.isDestroyed()) return;
  if (state.closed) {
    app.quit();
    return;
  }
  if (isDragging) return;
  const expanded = expandedBoundsFromState(state);
  isDocked = Boolean(state.docked && state.dock_edge);
  const nextBounds = isDocked ? collapsedBoundsFor(state.dock_edge, expanded) : expanded;
  const current = win.getBounds();
  if (
    current.x !== nextBounds.x ||
    current.y !== nextBounds.y ||
    current.width !== nextBounds.width ||
    current.height !== nextBounds.height
  ) {
    win.setBounds(nextBounds, false);
  }
  if (state.visible === false) {
    if (win.isVisible()) win.hide();
  } else if (!win.isVisible()) {
    win.showInactive();
  }
  setWindowMousePassthrough(isDocked && !dockMouseCaptured && !isDragging);
  sendDockState(isDocked ? state.dock_edge : "");
  const nextTopmost = state.always_on_top !== false;
  if (win.isAlwaysOnTop() !== nextTopmost) {
    win.setAlwaysOnTop(nextTopmost, "floating");
    win.setVisibleOnAllWorkspaces(nextTopmost, { visibleOnFullScreen: nextTopmost });
  }
  lastState = state;
}

function currentScalePercent() {
  if (!win || win.isDestroyed()) return 100;
  const bounds = isDocked ? expandedBoundsFromState(readState()) : win.getBounds();
  return Math.round((bounds.width / BASE_WIDTH) * 100);
}

function setPetScale(percent) {
  if (!win || win.isDestroyed()) return;
  if (isDocked) undockPetWindow();
  const scale = Math.max(0.5, Math.min(3, Number(percent || 100) / 100));
  const bounds = win.getBounds();
  const nextW = Math.round(BASE_WIDTH * scale);
  const nextH = Math.round(BASE_HEIGHT * scale);
  win.setBounds({ x: bounds.x, y: bounds.y, width: nextW, height: nextH }, false);
  writeState({
    x: bounds.x,
    y: bounds.y,
    w: nextW,
    h: nextH,
    electron_moved: true
  });
  if (tray) tray.setContextMenu(buildTrayMenu());
  scheduleViewerRefresh();
}

function resizePetBySteps(delta) {
  if (!win || win.isDestroyed()) return;
  const current = currentScalePercent();
  const next = Math.max(50, Math.min(300, current + (Number(delta || 0) > 0 ? 10 : -10)));
  setPetScale(next);
}

function scheduleViewerRefresh() {
  if (!win || win.isDestroyed()) return;
  setTimeout(() => {
    if (!win || win.isDestroyed()) return;
    win.webContents.send("pet-action", { action: "refresh-viewer" });
  }, 560);
}

function buildSizeMenuItems() {
  const current = currentScalePercent();
  return PET_SIZE_PRESETS.map((percent) => ({
    label: `${percent}%`,
    type: "radio",
    checked: Math.abs(current - percent) < 8,
    click: () => setPetScale(percent)
  }));
}

function setAlwaysOnTopEnabled(enabled) {
  if (!win || win.isDestroyed()) return;
  const value = Boolean(enabled);
  win.setAlwaysOnTop(value, "floating");
  win.setVisibleOnAllWorkspaces(value, { visibleOnFullScreen: value });
  writeState({ always_on_top: value });
  if (tray) tray.setContextMenu(buildTrayMenu());
}

function setLaunchAtLoginEnabled(enabled) {
  const value = Boolean(enabled);
  setStartupEnabled(value);
  writeState({ launch_at_login: value });
  if (tray) tray.setContextMenu(buildTrayMenu());
}

function hidePetWindow() {
  if (win && !win.isDestroyed()) win.hide();
  writeState({ visible: false, closed: false });
}

function startSync() {
  if (syncTimer) clearInterval(syncTimer);
  syncTimer = setInterval(() => applyState(readState()), 80);
}

function startCursorTracking() {
  if (cursorTimer) clearInterval(cursorTimer);
  cursorTimer = setInterval(() => {
    if (!win || win.isDestroyed() || !win.webContents) return;
    win.webContents.send("cursor-position", {
      cursor: screen.getCursorScreenPoint(),
      windowBounds: win.getBounds()
    });
  }, 33);
}

function buildContextMenu() {
  return Menu.buildFromTemplate([
    {
      label: t("chat"),
      click: () => {
        if (win && !win.isDestroyed()) {
          if (isDocked) undockPetWindow();
          win.webContents.send("pet-action", { action: "open-chat" });
        }
      }
    },
    {
      label: t("realtime"),
      click: () => openRealtimePrompt()
    },
    {
      label: t("talkToPets"),
      click: () => {
        if (win && !win.isDestroyed()) {
          win.webContents.send("pet-action", { action: "talk-to-pets" });
        }
      }
    },
    { type: "separator" },
    {
      label: t("openWeb"),
      click: () => shell.openExternal(WEB_URL)
    },
    {
      label: t("openLive2D"),
      click: () => shell.openExternal(WEB_URL + "/live2d")
    },
    {
      label: t("refresh"),
      click: () => scheduleViewerRefresh()
    },
    {
      label: isDocked ? t("edgeShow") : t("edgeHide"),
      click: () => toggleEdgeDock()
    },
    {
      label: t("alwaysOnTop"),
      type: "checkbox",
      checked: !win || win.isDestroyed() ? readState().always_on_top !== false : win.isAlwaysOnTop(),
      click: (item) => setAlwaysOnTopEnabled(item.checked)
    },
    {
      label: t("launchAtLogin"),
      type: "checkbox",
      checked: isStartupEnabled(),
      click: (item) => setLaunchAtLoginEnabled(item.checked)
    },
    {
      label: t("size"),
      submenu: buildSizeMenuItems()
    },
    { type: "separator" },
    {
      label: t("settings"),
      click: () => openSettingsWindow()
    },
    { type: "separator" },
    {
      label: t("closePet"),
      click: () => hidePetWindow()
    }
  ]);
}

function openRealtimePrompt() {
  shell.openExternal(WEB_URL + "/?realtime_prompt=1");
}

function openSettingsWindow() {
  if (settingsWin && !settingsWin.isDestroyed()) {
    settingsWin.show();
    settingsWin.focus();
    return;
  }
  settingsWin = new BrowserWindow({
    width: 520,
    height: 680,
    minWidth: 420,
    minHeight: 540,
    title: t("settingsTitle"),
    autoHideMenuBar: true,
    icon: iconPath() || undefined,
    backgroundColor: "#ffffff",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  });
  settingsWin.loadURL(WEB_URL + "/#settings");
  settingsWin.on("closed", () => {
    settingsWin = null;
  });
}

function buildTrayMenu() {
  return Menu.buildFromTemplate([
    {
      label: t("showPet"),
      click: () => {
        if (isDocked) {
          undockPetWindow();
        } else {
          if (win && !win.isDestroyed()) win.showInactive();
          writeState({ visible: true, closed: false });
        }
      }
    },
    {
      label: t("hidePet"),
      click: () => hidePetWindow()
    },
    { type: "separator" },
    {
      label: t("chat"),
      click: () => {
        if (win && !win.isDestroyed()) {
          if (isDocked) undockPetWindow();
          win.webContents.send("pet-action", { action: "open-chat" });
        }
      }
    },
    {
      label: t("realtime"),
      click: () => openRealtimePrompt()
    },
    {
      label: t("talkToPets"),
      click: () => startPetConversation()
    },
    {
      label: t("refresh"),
      click: () => scheduleViewerRefresh()
    },
    {
      label: isDocked ? t("edgeShow") : t("edgeHide"),
      click: () => toggleEdgeDock()
    },
    {
      label: t("alwaysOnTop"),
      type: "checkbox",
      checked: !win || win.isDestroyed() ? readState().always_on_top !== false : win.isAlwaysOnTop(),
      click: (item) => setAlwaysOnTopEnabled(item.checked)
    },
    {
      label: t("launchAtLogin"),
      type: "checkbox",
      checked: isStartupEnabled(),
      click: (item) => setLaunchAtLoginEnabled(item.checked)
    },
    {
      label: t("size"),
      submenu: buildSizeMenuItems()
    },
    { type: "separator" },
    {
      label: t("openSettings"),
      click: () => openSettingsWindow()
    },
    {
      label: t("quit"),
      click: () => {
        writeState({ closed: true });
        app.quit();
      }
    }
  ]);
}

function startTray() {
  const icon = iconPath();
  if (!icon) return;
  try {
    tray = new Tray(icon);
    tray.setToolTip(`Companion Pet - ${t("appName")}`);
    tray.setContextMenu(buildTrayMenu());
    tray.on("double-click", () => {
      if (isDocked) {
        undockPetWindow();
      } else {
        if (win && !win.isDestroyed()) win.showInactive();
        writeState({ visible: true, closed: false });
      }
    });
  } catch (_error) {
  }
}

function httpPostJson(endpoint, body) {
  return new Promise((resolve, reject) => {
    const url = new URL(endpoint, WEB_URL);
    const data = JSON.stringify(body);
    const options = {
      hostname: url.hostname,
      port: url.port || "59137",
      path: url.pathname + url.search,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Content-Length": Buffer.byteLength(data)
      }
    };
    const req = http.request(options, (res) => {
      let chunks = [];
      res.on("data", (chunk) => chunks.push(chunk));
      res.on("end", () => {
        const text = Buffer.concat(chunks).toString("utf8");
        try {
          resolve({ status: res.statusCode, data: JSON.parse(text) });
        } catch (_e) {
          resolve({ status: res.statusCode, data: text });
        }
      });
    });
    req.on("error", reject);
    req.write(data);
    req.end();
  });
}

async function fetchChatReply(message) {
  try {
    const result = await httpPostJson("/api/chat", {
      message,
      url: "",
      file_id: ""
    });
    if (result.status === 200 && result.data && result.data.reply) {
      return result.data.reply;
    }
    return "暂时想不出怎么回应你…";
  } catch (_err) {
    return "对话服务未连接，请稍后再试。";
  }
}

function stripReplyMetadata(text) {
  const raw = String(text || "").trim();
  if (!raw) return "";

  const kept = [];
  for (const part of raw.split(/\n\s*\n/)) {
    const trimmed = part.trim();
    if (!trimmed) continue;
    if (trimmed.includes("情感理解：") && trimmed.includes("回应策略：")) continue;
    if (trimmed.startsWith("我先判断这是") || trimmed.startsWith("我根据已学习的情感样本判断这是")) continue;
    kept.push(trimmed);
  }
  return kept.join("\n\n").trim() || raw;
}

function createWindow() {
  const style = argValue("--style", "live2d");
  geometryFile = argValue("--geometry-file", "");
  const state = readState();
  const url = state.url || `${WEB_URL}/${style === "3d" ? "3d" : "live2d"}?pet=1&shell=1`;
  const width = Math.max(120, Math.round(Number(state.w) || 250));
  const height = Math.max(160, Math.round(Number(state.h) || 350));

  win = new BrowserWindow({
    x: Math.round(Number(state.x) || 500),
    y: Math.round(Number(state.y) || 300),
    width,
    height,
    frame: false,
    transparent: true,
    alwaysOnTop: state.always_on_top !== false,
    hasShadow: false,
    resizable: false,
    minimizable: false,
    maximizable: false,
    fullscreenable: false,
    skipTaskbar: false,
    show: false,
    icon: iconPath() || undefined,
    backgroundColor: "#00000000",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      webviewTag: false,
      webSecurity: false,
      allowRunningInsecureContent: true,
      devTools: true
    }
  });

  win.setMenuBarVisibility(false);
  win.setAlwaysOnTop(state.always_on_top !== false, "floating");
  win.setVisibleOnAllWorkspaces(state.always_on_top !== false, { visibleOnFullScreen: state.always_on_top !== false });
  win.loadFile(path.join(__dirname, "shell.html"), { query: { url, style, locale: currentLocale() } });
  startTray();
  startTalkLoop();

  win.once("ready-to-show", () => {
    applyState(readState());
    win.showInactive();
  });

  win.on("move", () => {
    if (!win || win.isDestroyed() || isDocked || isDragging) return;
    const bounds = win.getBounds();
    scheduleWrite({
      x: bounds.x,
      y: bounds.y,
      w: bounds.width,
      h: bounds.height,
      electron_moved: true
    });
  });

  win.on("moved", () => {
    if (!win || win.isDestroyed() || isDocked || isDragging) return;
    const bounds = win.getBounds();
    scheduleWrite({
      x: bounds.x,
      y: bounds.y,
      w: bounds.width,
      h: bounds.height,
      electron_moved: true
    });
  });

  ipcMain.on("pet:drag-start", (_event, { offsetX, offsetY }) => {
    if (isDocked) undockPetWindow();
    isDragging = true;
    dragOffset = { x: offsetX, y: offsetY };
  });

  ipcMain.on("pet:drag-move", (_event, { screenX, screenY }) => {
    if (!win || win.isDestroyed() || !isDragging) return;
    win.setPosition(
      Math.round(screenX - dragOffset.x),
      Math.round(screenY - dragOffset.y),
      false
    );
  });

  ipcMain.on("pet:drag-end", () => {
    isDragging = false;
    if (!win || win.isDestroyed()) return;
    const edge = detectDockEdge(win.getBounds());
    if (edge) {
      dockPetWindow(edge);
    } else {
      persistCurrentWindowBounds({
        docked: false,
        dock_edge: "",
        visible: true,
        closed: false
      });
    }
  });

  ipcMain.on("pet:dock-drag-start", (_event, { offsetX, offsetY, screenX, screenY }) => {
    if (!win || win.isDestroyed() || !isDocked) return;
    isDragging = true;
    dockMouseCaptured = true;
    setWindowMousePassthrough(false);
    dockDragOffset = {
      x: Math.round(Number(offsetX) || 0),
      y: Math.round(Number(offsetY) || 0)
    };
    dockDragStart = {
      x: Math.round(Number(screenX) || 0),
      y: Math.round(Number(screenY) || 0)
    };
  });

  ipcMain.on("pet:dock-drag-move", (_event, { screenX, screenY }) => {
    if (!win || win.isDestroyed() || !isDragging) return;
    const x = Math.round(Number(screenX) || 0);
    const y = Math.round(Number(screenY) || 0);
    if (isDocked) {
      moveDockedWindow(x, y);
      return;
    }
    win.setPosition(
      Math.round(x - dragOffset.x),
      Math.round(y - dragOffset.y),
      false
    );
  });

  ipcMain.on("pet:dock-drag-end", () => {
    if (!win || win.isDestroyed()) return;
    isDragging = false;
    if (isDocked) {
      persistDockedWindowPosition();
    } else {
      const edge = detectDockEdge(win.getBounds());
      if (edge) {
        dockPetWindow(edge);
      } else {
        persistCurrentWindowBounds({
          docked: false,
          dock_edge: "",
          visible: true,
          closed: false
        });
      }
    }
    dockMouseCaptured = false;
    setWindowMousePassthrough(isDocked);
    sendDockState(isDocked ? readState().dock_edge : "");
  });

  ipcMain.on("pet:set-mouse-passthrough", (_event, { active }) => {
    dockMouseCaptured = isDocked && !Boolean(active);
    setWindowMousePassthrough(Boolean(active) && isDocked && !isDragging);
  });

  ipcMain.on("pet:right-click", (_event, { x, y }) => {
    const menu = buildContextMenu();
    menu.popup({
      window: win,
      x: Math.round(x),
      y: Math.round(y),
      callback: () => {
        if (win && !win.isDestroyed()) {
          win.webContents.send("pet-action", { action: "menu-closed" });
        }
      }
    });
  });

  ipcMain.on("pet:hover-change", (_event, { active, text }) => {
    hoverState = { active, chat: text || "" };
  });

  ipcMain.handle("pet:chat-send", async (_event, message) => {
    if (chatBusy) return { reply: "等等，我正在想…", busy: true };
    chatBusy = true;
    const reply = stripReplyMetadata(await fetchChatReply(message));
    chatHistory.push([message, reply]);
    if (chatHistory.length > 50) chatHistory = chatHistory.slice(-50);
    chatBusy = false;
    return { reply, busy: false };
  });

  ipcMain.on("pet:talk-to-pets", () => {
    startPetConversation();
  });

  ipcMain.on("pet:resize-by", (_event, { delta }) => {
    resizePetBySteps(delta);
  });

  ipcMain.on("pet:undock", () => {
    undockPetWindow();
  });

  ipcMain.on("pet:open-web", (_event, url) => {
    shell.openExternal(url || WEB_URL);
  });

  startSync();
  startCursorTracking();
}

ipcMain.on("pet-shell-ready", () => {
  if (win && !win.isDestroyed()) applyState(readState());
});

app.commandLine.appendSwitch("disable-gpu-sandbox");
app.commandLine.appendSwitch("autoplay-policy", "no-user-gesture-required");
app.setAppUserModelId("CompanionAI.Pet");
app.whenReady().then(createWindow);
app.on("window-all-closed", () => app.quit());
app.on("before-quit", () => {
  if (syncTimer) clearInterval(syncTimer);
  if (cursorTimer) clearInterval(cursorTimer);
  if (talkTimer) clearInterval(talkTimer);
  if (writeTimer) clearTimeout(writeTimer);
  if (tray) tray.destroy();
  if (settingsWin && !settingsWin.isDestroyed()) settingsWin.destroy();
});
