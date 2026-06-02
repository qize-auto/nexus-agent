/**
 * NexusAgent Desktop v3.3 — Electron 主进程
 * 职责: 窗口管理 / Python后端守护 / 系统托盘 / 全局快捷键 / 通知 / 崩溃恢复
 */

const {
  app, BrowserWindow, Tray, Menu, nativeImage,
  dialog, globalShortcut, ipcMain, Notification,
  shell, screen,
} = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');

// ── 常量 ────────────────────────────────────────────────────────
const SERVER_PORT = 8080;
const SERVER_URL = `http://127.0.0.1:${SERVER_PORT}`;
const WINDOW_STATE_FILE = path.join(app.getPath('userData'), 'window-state.json');
const MAX_SERVER_RESTARTS = 3;
const SERVER_RESTART_WINDOW_MS = 30000; // 30秒内多次崩溃则放弃

// ── 状态 ────────────────────────────────────────────────────────
let mainWindow = null;
let tray = null;
let serverProcess = null;
let serverErrors = [];
let serverRestartCount = 0;
let serverRestartTimestamps = [];
let isQuitting = false;
let isServerReady = false;

// ── 工具函数 ────────────────────────────────────────────────────

function findPython() {
  const candidates = process.platform === 'win32'
    ? ['python.exe', 'python3.exe', 'py.exe']
    : ['python3', 'python'];
  for (const cmd of candidates) {
    try {
      const result = require('child_process').spawnSync(cmd, ['--version'], {
        timeout: 3000, shell: process.platform === 'win32',
      });
      if (result.status === 0) return cmd;
    } catch (e) { /* ignore */ }
  }
  return null;
}

function loadWindowState() {
  try {
    if (fs.existsSync(WINDOW_STATE_FILE)) {
      return JSON.parse(fs.readFileSync(WINDOW_STATE_FILE, 'utf-8'));
    }
  } catch (e) { console.error('[State] Load failed:', e.message); }
  return {
    width: 1280, height: 840,
    x: undefined, y: undefined,
    maximized: false,
  };
}

function saveWindowState() {
  if (!mainWindow) return;
  const bounds = mainWindow.getNormalBounds();
  const state = {
    width: bounds.width,
    height: bounds.height,
    x: bounds.x,
    y: bounds.y,
    maximized: mainWindow.isMaximized(),
  };
  try {
    fs.writeFileSync(WINDOW_STATE_FILE, JSON.stringify(state), 'utf-8');
  } catch (e) { console.error('[State] Save failed:', e.message); }
}

function createAppIcon(size = 32) {
  // 生成简洁的 "N" 字母图标（深蓝背景 + 青色 N）
  const canvas = document = undefined; // 使用原生 Image/Canvas API 不可用，改用 buffer
  // 使用原生Image构造一个内联PNG
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 100 100">
      <rect width="100" height="100" rx="20" fill="#0d1117"/>
      <text x="50" y="72" font-family="Arial Black, sans-serif" font-size="60" font-weight="900"
            text-anchor="middle" fill="#58a6ff">N</text>
    </svg>`;
  return nativeImage.createFromBuffer(Buffer.from(svg)).resize({ width: size, height: size });
}

// ── Python 后端管理 ─────────────────────────────────────────────

function startPythonServer() {
  const python = findPython();
  if (!python) {
    dialog.showErrorBox('Python 未找到',
      'NexusAgent 需要 Python 3.10+ 才能运行。\n\n' +
      '请从 https://www.python.org/downloads/ 下载安装，\n' +
      '并确保勾选 "Add Python to PATH"。');
    app.quit();
    return;
  }

  const serverScript = path.join(__dirname, 'run_web.py');
  if (!fs.existsSync(serverScript)) {
    dialog.showErrorBox('文件缺失', `未找到服务端脚本:\n${serverScript}`);
    app.quit();
    return;
  }

  console.log('[Server] Starting Python backend...');
  serverProcess = spawn(python, [serverScript], {
    cwd: __dirname,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, NEXUS_DESKTOP_MODE: '1' },
  });

  serverProcess.stdout.on('data', (data) => {
    const msg = data.toString().trim();
    if (msg) console.log('[Server]', msg);
  });

  serverProcess.stderr.on('data', (data) => {
    const msg = data.toString().trim();
    if (msg) {
      serverErrors.push(msg);
      console.error('[Server Error]', msg);
    }
  });

  serverProcess.on('error', (err) => {
    console.error('[Server] Failed to start:', err.message);
    serverErrors.push('Failed to start: ' + err.message);
  });

  serverProcess.on('close', (code) => {
    console.log('[Server] Exited with code', code);
    isServerReady = false;
    if (code !== 0 && code !== null && !isQuitting) {
      serverErrors.push(`Server crashed (exit code ${code})`);
      handleServerCrash();
    }
  });
}

function stopPythonServer() {
  if (serverProcess) {
    serverProcess.kill();
    serverProcess = null;
    isServerReady = false;
  }
}

function handleServerCrash() {
  const now = Date.now();
  serverRestartTimestamps = serverRestartTimestamps.filter(t => now - t < SERVER_RESTART_WINDOW_MS);
  serverRestartTimestamps.push(now);

  if (serverRestartTimestamps.length > MAX_SERVER_RESTARTS) {
    dialog.showErrorBox('后端服务异常',
      'Python 后端在短时间内多次崩溃，已停止自动重启。\n\n' +
      '最近错误:\n' + serverErrors.slice(-5).join('\n'));
    app.quit();
    return;
  }

  if (mainWindow) {
    mainWindow.webContents.send('server-status', { status: 'reconnecting', attempt: serverRestartTimestamps.length });
  }

  setTimeout(() => {
    if (!isQuitting) {
      console.log('[Server] Auto-restarting...');
      startPythonServer();
      waitForServer().then(() => {
        isServerReady = true;
        if (mainWindow) {
          mainWindow.webContents.send('server-status', { status: 'ready' });
        }
      }).catch(() => {
        // 等待失败会在下一轮 crash 处理中解决
      });
    }
  }, 2000);
}

function waitForServer(retries = 40, interval = 500) {
  return new Promise((resolve, reject) => {
    function check() {
      http.get(SERVER_URL + '/api/health', (res) => {
        if (res.statusCode === 200) {
          resolve();
        } else {
          retry();
        }
      }).on('error', retry);
    }
    function retry() {
      retries--;
      if (retries > 0) {
        setTimeout(check, interval);
      } else {
        const errors = serverErrors.slice(-5).join('\n') || 'No error output from server';
        reject(new Error(`Server did not start after ${(40 - retries) * interval / 1000}s.\n\nServer errors:\n${errors}`));
      }
    }
    check();
  });
}

// ── 窗口管理 ────────────────────────────────────────────────────

function createWindow() {
  const state = loadWindowState();
  const primaryDisplay = screen.getPrimaryDisplay();
  const { width: screenW, height: screenH } = primaryDisplay.workAreaSize;

  // 确保窗口在屏幕可见区域内
  let x = state.x;
  let y = state.y;
  if (x !== undefined && y !== undefined) {
    if (x < 0 || x + state.width > screenW) x = undefined;
    if (y < 0 || y + state.height > screenH) y = undefined;
  }

  mainWindow = new BrowserWindow({
    width: state.width || 1280,
    height: state.height || 840,
    x, y,
    minWidth: 800,
    minHeight: 500,
    title: 'NexusAgent',
    backgroundColor: '#0d1117',
    show: false, // 等 ready-to-show 再显示，避免白屏
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      spellcheck: false,
    },
    icon: createAppIcon(256),
  });

  mainWindow.loadURL(SERVER_URL + '/desktop/index.html');

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    if (state.maximized) mainWindow.maximize();
  });

  mainWindow.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow.hide();
      // macOS 上隐藏到 Dock，Windows/Linux 隐藏到托盘
      if (process.platform === 'darwin') {
        app.dock.hide();
      }
    } else {
      saveWindowState();
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  // 拦截新窗口请求，用系统浏览器打开外部链接
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http')) shell.openExternal(url);
    return { action: 'deny' };
  });

  // 开发工具（开发环境）
  if (process.env.NEXUS_DEBUG === '1') {
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  }
}

function showWindow() {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.show();
    mainWindow.focus();
    if (process.platform === 'darwin') app.dock.show();
  } else {
    createWindow();
  }
}

// ── 系统托盘 ────────────────────────────────────────────────────

function createTray() {
  // 使用 16x16 / 32x32 图标
  const icon = createAppIcon(16);
  tray = new Tray(icon);
  tray.setToolTip('NexusAgent v3.3');

  const contextMenu = Menu.buildFromTemplate([
    {
      label: '显示 NexusAgent',
      click: () => showWindow(),
    },
    { type: 'separator' },
    {
      label: '新对话',
      click: () => {
        showWindow();
        mainWindow?.webContents.send('menu-new-chat');
      },
    },
    {
      label: '设置',
      click: () => {
        showWindow();
        mainWindow?.webContents.send('menu-open-settings');
      },
    },
    { type: 'separator' },
    {
      label: '退出',
      click: () => {
        isQuitting = true;
        app.quit();
      },
    },
  ]);

  tray.setContextMenu(contextMenu);
  tray.on('double-click', () => showWindow());
  tray.on('click', () => {
    // Windows: 单击切换显示/隐藏
    if (process.platform === 'win32') {
      if (mainWindow && mainWindow.isVisible()) {
        mainWindow.hide();
      } else {
        showWindow();
      }
    }
  });
}

// ── IPC 通信 ────────────────────────────────────────────────────

ipcMain.handle('app-version', () => app.getVersion());

ipcMain.handle('show-notification', (_event, { title, body }) => {
  if (Notification.isSupported()) {
    const n = new Notification({
      title: title || 'NexusAgent',
      body: body || '',
      icon: createAppIcon(128),
    });
    n.on('click', () => showWindow());
    n.show();
  }
});

ipcMain.handle('open-external', (_event, url) => {
  if (typeof url === 'string' && url.startsWith('http')) {
    shell.openExternal(url);
  }
});

ipcMain.on('window-minimize', () => mainWindow?.minimize());
ipcMain.on('window-maximize', () => {
  if (mainWindow?.isMaximized()) mainWindow.unmaximize();
  else mainWindow?.maximize();
});
ipcMain.on('window-close', () => mainWindow?.hide());

// ── 应用生命周期 ────────────────────────────────────────────────

app.setAppUserModelId('com.nexusagent.desktop');

app.whenReady().then(async () => {
  // 单实例锁定
  const gotLock = app.requestSingleInstanceLock();
  if (!gotLock) {
    app.quit();
    return;
  }

  app.on('second-instance', () => {
    showWindow();
  });

  // 全局快捷键: Ctrl+Shift+N (或 Cmd+Shift+N) 显示/隐藏
  const shortcut = process.platform === 'darwin' ? 'Cmd+Shift+N' : 'Ctrl+Shift+N';
  globalShortcut.register(shortcut, () => {
    if (mainWindow && mainWindow.isVisible() && mainWindow.isFocused()) {
      mainWindow.hide();
    } else {
      showWindow();
    }
  });

  // 启动 Python 后端
  startPythonServer();

  try {
    await waitForServer();
    isServerReady = true;
    console.log('[App] Backend ready');
  } catch (e) {
    dialog.showErrorBox('启动失败',
      '无法连接到 NexusAgent 后端服务。\n\n' + e.message);
    stopPythonServer();
    app.quit();
    return;
  }

  createWindow();
  createTray();
});

app.on('before-quit', () => {
  isQuitting = true;
  globalShortcut.unregisterAll();
  saveWindowState();
  stopPythonServer();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    // Windows/Linux: 窗口关闭时隐藏到托盘，不退出
    // macOS: 保留在 Dock 中
  }
});

app.on('activate', () => {
  if (mainWindow === null) createWindow();
  else showWindow();
});

// 捕获未处理异常
process.on('uncaughtException', (err) => {
  console.error('[Main] Uncaught exception:', err);
});
process.on('unhandledRejection', (reason) => {
  console.error('[Main] Unhandled rejection:', reason);
});
