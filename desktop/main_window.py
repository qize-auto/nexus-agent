"""
NexusAgent Desktop — PyQt6 桌面客户端主窗口
全新 UI：单页面现代化设计，加载 desktop/index.html
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout,
    QSystemTrayIcon, QMenu, QApplication, QMessageBox,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import QUrl, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QPixmap, QPainter, QColor

from .bridge import NexusBridge
from .worker import AgentWorker


class NexusMainWindow(QMainWindow):
    """NexusAgent 桌面主窗口 — 全新单页面 UI"""

    def __init__(self, agent=None, config=None):
        super().__init__()
        self._agent = agent
        self._config = config
        self._worker: AgentWorker | None = None
        self._session_counter = 0

        self._setup_ui()
        self._setup_tray()
        self._load_page()

    def _setup_ui(self):
        self.setWindowTitle("NexusAgent")
        self.setGeometry(120, 80, 1100, 760)
        self.setMinimumSize(720, 480)

        cw = QWidget(self)
        self.setCentralWidget(cw)
        layout = QVBoxLayout(cw)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 单一 Web 视图，加载完整的单页面应用
        self.web_view = QWebEngineView(self)
        layout.addWidget(self.web_view)

        self._build_menu()

    def _load_page(self):
        """加载桌面 UI"""
        page_path = Path(__file__).parent / "index.html"
        if page_path.exists():
            self.web_view.load(QUrl.fromLocalFile(str(page_path.resolve())))
        else:
            self.web_view.setHtml(
                "<body style='background:#0f0f0f;color:#ececec;font-family:sans-serif;padding:40px'>"
                "<h2>UI 文件未找到</h2><p>请确认 desktop/index.html 存在</p></body>"
            )
        QTimer.singleShot(800, self._setup_bridge)

    def _setup_bridge(self):
        """建立 JS ↔ Python 桥接"""
        self.channel = QWebChannel(self)
        self.bridge = NexusBridge(parent=self, agent=self._agent, config=self._config)
        self.channel.registerObject("agentBridge", self.bridge)
        self.web_view.page().setWebChannel(self.channel)

    def _build_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("文件")
        act_exit = QAction("退出", self)
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        model_menu = menubar.addMenu("模型")
        for m in ["moonshot-v1-8k", "moonshot-v1-32k", "deepseek-chat", "deepseek-v4-pro"]:
            act = QAction(m, self)
            act.triggered.connect(lambda checked, model=m: self._switch_model(model))
            model_menu.addAction(act)

        view_menu = menubar.addMenu("视图")
        act_reload = QAction("刷新界面", self)
        act_reload.triggered.connect(self._load_page)
        view_menu.addAction(act_reload)

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setToolTip("NexusAgent")
        self.tray.setIcon(self._create_tray_icon())
        self.tray.setVisible(True)

        menu = QMenu(self)
        act_show = QAction("显示", self)
        act_show.triggered.connect(self.showNormal)
        menu.addAction(act_show)
        act_quit = QAction("退出", self)
        act_quit.triggered.connect(QApplication.instance().quit)
        menu.addAction(act_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)

    def _create_tray_icon(self) -> QIcon:
        """生成纯色托盘图标（无外部资源依赖）"""
        pixmap = QPixmap(32, 32)
        pixmap.fill(QColor("#10a37f"))
        painter = QPainter(pixmap)
        painter.setPen(QColor("#ffffff"))
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(10, 10, 12, 12)
        painter.end()
        return QIcon(pixmap)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.showNormal()
            self.raise_()

    # ── Agent 执行 ───────────────────────────────────────

    def _run_agent(self, user_input: str):
        """启动后台 Agent 线程"""
        if self._worker and self._worker.isRunning():
            self._run_js('uiAPI.showToast("Agent 正在处理中…")')
            return

        self._session_counter += 1
        session_id = f"desktop_{self._session_counter}"

        self._worker = AgentWorker(self._agent, user_input, session_id)
        self._worker.turnFinished.connect(self._on_worker_finished)
        self._worker.errorOccurred.connect(self._on_worker_error)
        self._worker.start()

        self._run_js('uiAPI.setStatus("thinking", "思考中…")')

    def _on_worker_finished(self, result):
        result_text = str(result) if result else ""
        # 转义 JSON 字符串中的特殊字符
        safe = json.dumps(result_text)
        self._run_js(f'uiAPI.addAgentMessage({safe})')
        self._worker = None

    def _on_worker_error(self, error: str):
        safe = json.dumps(error)
        self._run_js(f'uiAPI.addError({safe})')
        self._worker = None

    # ── 模型切换 ─────────────────────────────────────────

    def _switch_model(self, model: str):
        if self._config:
            self._config.model.default_model = model
            self._config.model.default_provider = (
                "moonshot" if model.startswith("moonshot") else "deepseek"
            )
        safe = json.dumps(model)
        self._run_js(f'uiAPI.showToast("已切换模型: " + {safe})')

    def _reload_page(self):
        self._load_page()

    # ── JS 通信 ──────────────────────────────────────────

    def _run_js(self, js: str):
        """在 Web 视图中执行 JS"""
        self.web_view.page().runJavaScript(js)

    # ── 窗口事件 ─────────────────────────────────────────

    def closeEvent(self, event):
        event.accept()
