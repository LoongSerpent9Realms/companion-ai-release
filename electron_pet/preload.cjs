const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("petShell", {
  ready() {
    ipcRenderer.send("pet-shell-ready");
  },

  onCursorPosition(callback) {
    ipcRenderer.on("cursor-position", (_event, payload) => {
      if (typeof callback === "function") callback(payload);
    });
  },

  onPetAction(callback) {
    ipcRenderer.on("pet-action", (_event, payload) => {
      if (typeof callback === "function") callback(payload);
    });
  },

  dragStart(offsetX, offsetY) {
    ipcRenderer.send("pet:drag-start", { offsetX, offsetY });
  },

  dragMove(screenX, screenY) {
    ipcRenderer.send("pet:drag-move", { screenX, screenY });
  },

  dragEnd() {
    ipcRenderer.send("pet:drag-end");
  },

  dockDragStart(offsetX, offsetY, screenX, screenY) {
    ipcRenderer.send("pet:dock-drag-start", { offsetX, offsetY, screenX, screenY });
  },

  dockDragMove(screenX, screenY) {
    ipcRenderer.send("pet:dock-drag-move", { screenX, screenY });
  },

  dockDragEnd() {
    ipcRenderer.send("pet:dock-drag-end");
  },

  setMousePassthrough(active) {
    ipcRenderer.send("pet:set-mouse-passthrough", { active });
  },

  rightClick(x, y) {
    ipcRenderer.send("pet:right-click", { x, y });
  },

  setHover(active, text) {
    ipcRenderer.send("pet:hover-change", { active, text: text || "" });
  },

  async sendChat(message) {
    return await ipcRenderer.invoke("pet:chat-send", message);
  },

  talkToPets() {
    ipcRenderer.send("pet:talk-to-pets");
  },

  resizeBy(delta) {
    ipcRenderer.send("pet:resize-by", { delta });
  },

  undock() {
    ipcRenderer.send("pet:undock");
  },

  openWeb(url) {
    ipcRenderer.send("pet:open-web", url);
  }
});
