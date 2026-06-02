/**
 * NexusAgent Desktop v3.3 — Preload 脚本
 * 在隔离的渲染进程中暴露安全的 API 给前端使用
 */

const { contextBridge, ipcRenderer } = require('electron');

// 暴露给 window.nexusDesktop 的 API
contextBridge.exposeInMainWorld('nexusDesktop', {
  // ── 应用信息 ──
  appVersion: process.env.npm_package_version || '3.3.0',
  platform: process.platform,

  // ── 后端通信 ──
  serverURL: 'http://127.0.0.1:8080',

  // ── IPC 调用 ──
  invoke: (channel, ...args) => {
    const validChannels = ['app-version', 'show-notification', 'open-external'];
    if (validChannels.includes(channel)) {
      return ipcRenderer.invoke(channel, ...args);
    }
    return Promise.reject(new Error(`Invalid channel: ${channel}`));
  },

  send: (channel, ...args) => {
    const validChannels = ['window-minimize', 'window-maximize', 'window-close'];
    if (validChannels.includes(channel)) {
      ipcRenderer.send(channel, ...args);
    }
  },

  // ── 事件监听 ──
  on: (channel, callback) => {
    const validChannels = [
      'server-status',
      'menu-new-chat',
      'menu-open-settings',
    ];
    if (validChannels.includes(channel)) {
      const wrapper = (_event, ...args) => callback(...args);
      ipcRenderer.on(channel, wrapper);
      // 返回取消订阅函数
      return () => ipcRenderer.removeListener(channel, wrapper);
    }
    return () => {};
  },

  // ── 通知 ──
  notify: (title, body) => {
    ipcRenderer.invoke('show-notification', { title, body });
  },

  // ── 打开外部链接 ──
  openExternal: (url) => {
    ipcRenderer.invoke('open-external', url);
  },
});
