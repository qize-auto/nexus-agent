/**
 * NexusAgent Desktop v3.3 — 前端应用逻辑
 * 支持三种运行环境：Electron / PyQt6 QWebEngineView / 纯 Web
 */

(function() {
  'use strict';

  // ═══════════════════════════════════════════════
  // 常量与环境检测
  // ═══════════════════════════════════════════════

  const API_BASE = 'http://127.0.0.1:8080/api';
  const STORAGE_KEY = 'nexus_sessions_v3';
  const STORAGE_THEME = 'nexus_theme';
  const MAX_SESSIONS = 50;
  const STORAGE_LANG = 'nexus_lang';

  // ═══════════════════════════════════════════════
  // 国际化 (I18N)
  // ═══════════════════════════════════════════════

  const I18N = {
    en: {
      'sidebar.new_chat': 'New Chat',
      'sidebar.diagnostics': 'Diagnostics',
      'sidebar.settings': 'Settings',
      'topbar.toggle_sidebar': 'Collapse/Expand Sidebar',
      'topbar.clear_chat': 'Clear Chat',
      'welcome.subtitle': 'Local-first Personal Agent System',
      'welcome.card_qa_title': 'Smart Q&A',
      'welcome.card_qa_desc': 'Natural language understanding & generation powered by LLMs',
      'welcome.card_privacy_title': 'Privacy Protection',
      'welcome.card_privacy_desc': 'Local data storage with automatic PII redaction',
      'welcome.card_tools_title': 'Tool Invocation',
      'welcome.card_tools_desc': 'Code execution, file analysis, web requests',
      'input.placeholder': 'Message NexusAgent…',
      'input.hint': 'Enter to send · Shift+Enter newline · 📎 Upload file',
      'settings.title': 'Settings',
      'settings.interface': 'Interface',
      'settings.language': 'Language',
      'settings.theme': 'Theme',
      'settings.provider': 'Model Provider',
      'settings.model': 'Model',
      'settings.api_key': 'API Key',
      'settings.show_hide': 'Show/Hide',
      'settings.api_key_hint': 'Leave empty to use .env configuration',
      'settings.ollama_host': 'Ollama Host',
      'settings.ollama_hint': 'Only applies when using Ollama',
      'settings.security': 'Security',
      'settings.diagnostics': 'Diagnostics',
      'settings.save': 'Save',
      'provider.ollama': 'Ollama (Local)',
      'provider.moonshot': 'Moonshot',
      'provider.deepseek': 'DeepSeek',
      'provider.openai': 'OpenAI',
      'badge.input_sanitization': 'Input Sanitization',
      'badge.pii_redaction': 'PII Redaction',
      'theme.dark': 'Dark',
      'theme.light': 'Light',
      'theme.system': 'System',
      'diag.title': 'Diagnostics',
      'diag.auto_refresh': 'Auto-refresh',
      'diag.system_health': 'System Health',
      'diag.health_dashboard': 'Health Dashboard',
      'diag.health_desc': 'Backend health, metrics, security status',
      'diag.run': 'Run',
      'diag.connectivity_test': 'Connectivity Test',
      'diag.connectivity_desc': 'Tool registry & module import checks',
      'diag.module_status': 'Module Status',
      'diag.module_desc': 'Core module availability report',
      'diag.analysis': 'Analysis',
      'diag.audit_viewer': 'Audit Viewer',
      'diag.audit_desc': 'Security events & execution traces',
      'diag.ux_advisor': 'UX Advisor',
      'diag.ux_desc': 'Configuration UX analysis',
      'diag.compare': 'Compare',
      'diag.design_diff': '🎨 Design Diff',
      'diag.baseline_placeholder': 'Baseline design spec…',
      'diag.current_placeholder': 'Current design spec…',
      'diag.compare_btn': 'Compare',
      'diag.competitor_analysis': '🏆 Competitor Analysis',
      'diag.competitor_name': 'Competitor name',
      'diag.ours_placeholder': 'Our features (one per line)…',
      'diag.theirs_placeholder': 'Competitor features (one per line)…',
      'diag.analyze_btn': 'Analyze',
      'diag.alerts': 'Alerts',
      'diag.load': 'Load',
      'diag.export': 'Export',
      'diag.export_btn': 'Export',
      'diag.history': 'History',
      'filter.all': 'All',
      'filter.critical': 'Critical',
      'filter.error': 'Error',
      'filter.warning': 'Warning',
      'filter.info': 'Info',
      'format.markdown': 'Markdown',
      'format.json': 'JSON',
      'loading.connecting': 'Connecting to backend…',
      'session.empty': 'No conversations yet',
      'session.confirm_delete': 'Delete this conversation?',
      'session.welcome': 'Welcome',
      'session.new_chat': 'New Chat',
      'status.thinking': 'Thinking…',
      'status.ready': 'Ready',
      'status.offline': 'Offline',
      'status.error': 'Error',
      'upload.uploading': 'Uploading…',
      'upload.converted': 'File converted',
      'upload.ready': 'is ready',
      'upload.failed': 'Upload failed',
      'upload.too_large': 'File too large',
      'upload.size_limit': 'Max 20MB per file',
      'action.copy': 'Copy',
      'action.copied': 'Copied',
      'error.request_failed': 'Request failed',
      'error.connection_failed': 'Connection failed',
      'error.network': 'Network error',
      'error.unknown': 'Unknown error',
      'error.generic': 'Error',
      'settings.saved': 'Config saved',
      'settings.save_failed': 'Save failed',
      'avatar.user': 'Me',
'alert.dismiss': 'Dismiss',
      // Document Editor
      'sidebar.documents': 'Documents',
      'doc_editor.title': 'Documents',
      'doc_editor.new': 'New',
      'doc_editor.edit': 'Edit',
      'doc_editor.preview': 'Preview',
      'doc_editor.ai_assist': '✨ Ask AI',
      'doc_editor.download': 'Download',
      'doc_editor.placeholder': 'Write Markdown here...',
      'doc_editor.untitled': 'Untitled',
      'doc_editor.confirm_delete': 'Delete this document?',
    },
    zh: {
      'sidebar.new_chat': '新对话',
      'sidebar.diagnostics': '诊断',
      'sidebar.settings': '设置',
      'topbar.toggle_sidebar': '收起/展开边栏',
      'topbar.clear_chat': '清空对话',
      'welcome.subtitle': '本地优先的个人智能体系统',
      'welcome.card_qa_title': '智能问答',
      'welcome.card_qa_desc': '基于大模型的自然语言理解与生成',
      'welcome.card_privacy_title': '隐私保护',
      'welcome.card_privacy_desc': '数据本地存储，PII 自动脱敏',
      'welcome.card_tools_title': '工具调用',
      'welcome.card_tools_desc': '代码执行、文件分析、网络请求',
      'input.placeholder': '发送消息给 NexusAgent…',
      'input.hint': 'Enter 发送 · Shift+Enter 换行 · 📎 上传文件',
      'settings.title': '设置',
      'settings.interface': '界面',
      'settings.language': '语言',
      'settings.theme': '主题',
      'settings.provider': '模型提供商',
      'settings.model': '模型',
      'settings.api_key': 'API Key',
      'settings.show_hide': '显示/隐藏',
      'settings.api_key_hint': '留空则使用 .env 文件中的配置',
      'settings.ollama_host': 'Ollama 主机地址',
      'settings.ollama_hint': '仅在使用 Ollama 时生效',
      'settings.security': '安全状态',
      'settings.diagnostics': '诊断配置',
      'settings.save': '保存配置',
      'provider.ollama': 'Ollama (本地)',
      'provider.moonshot': 'Moonshot (月之暗面)',
      'provider.deepseek': 'DeepSeek',
      'provider.openai': 'OpenAI',
      'badge.input_sanitization': '输入消毒',
      'badge.pii_redaction': 'PII 脱敏',
      'theme.dark': '深色',
      'theme.light': '浅色',
      'theme.system': '跟随系统',
      'diag.title': 'Diagnostics',
      'diag.auto_refresh': '自动刷新',
      'diag.system_health': '系统健康',
      'diag.health_dashboard': '健康看板',
      'diag.health_desc': '后端健康、指标、安全状态',
      'diag.run': '运行',
      'diag.connectivity_test': '连接测试',
      'diag.connectivity_desc': '工具注册表与模块导入检查',
      'diag.module_status': '模块状态',
      'diag.module_desc': '核心模块可用性报告',
      'diag.analysis': '分析',
      'diag.audit_viewer': '审计查看器',
      'diag.audit_desc': '安全事件与执行追踪',
      'diag.ux_advisor': 'UX 顾问',
      'diag.ux_desc': '配置 UX 分析',
      'diag.compare': '对比',
      'diag.design_diff': '🎨 设计对比',
      'diag.baseline_placeholder': '基线设计规范…',
      'diag.current_placeholder': '当前设计规范…',
      'diag.compare_btn': '对比',
      'diag.competitor_analysis': '🏆 竞品分析',
      'diag.competitor_name': '竞品名称',
      'diag.ours_placeholder': '我们的功能（每行一个）…',
      'diag.theirs_placeholder': '竞品功能（每行一个）…',
      'diag.analyze_btn': '分析',
      'diag.alerts': '告警',
      'diag.load': '加载',
      'diag.export': '导出',
      'diag.export_btn': '导出',
      'diag.history': '历史',
      'filter.all': '全部',
      'filter.critical': '严重',
      'filter.error': '错误',
      'filter.warning': '警告',
      'filter.info': '信息',
      'format.markdown': 'Markdown',
      'format.json': 'JSON',
      'loading.connecting': '正在连接后端服务…',
      'session.empty': '暂无对话',
      'session.confirm_delete': '确定删除此对话？',
      'session.welcome': '欢迎',
      'session.new_chat': '新对话',
      'status.thinking': '思考中…',
      'status.ready': '就绪',
      'status.offline': '离线',
      'status.error': '出错',
      'upload.uploading': '上传中…',
      'upload.converted': '文件已转换',
      'upload.ready': '已准备就绪',
      'upload.failed': '上传失败',
      'upload.too_large': '文件过大',
      'upload.size_limit': '单文件上限 20MB',
      'action.copy': '复制',
      'action.copied': '已复制',
      'error.request_failed': '请求失败',
      'error.connection_failed': '连接失败',
      'error.network': '网络错误',
      'error.unknown': '未知错误',
      'error.generic': '错误',
      'settings.saved': '配置已保存并生效',
      'settings.save_failed': '保存失败',
      'avatar.user': '我',
'alert.dismiss': '关闭',
      // 文档编辑器
      'sidebar.documents': '文档',
      'doc_editor.title': '文档',
      'doc_editor.new': '新建',
      'doc_editor.edit': '编辑',
      'doc_editor.preview': '预览',
      'doc_editor.ai_assist': '✨ 问 AI',
      'doc_editor.download': '下载',
      'doc_editor.placeholder': '在此输入 Markdown...',
      'doc_editor.untitled': '未命名',
      'doc_editor.confirm_delete': '删除此文档？',
    }
  };

  let currentLang = localStorage.getItem(STORAGE_LANG) || (navigator.language.startsWith('zh') ? 'zh' : 'en');

  function t(key, fallback) {
    const dict = I18N[currentLang] || I18N.en;
    return dict[key] !== undefined ? dict[key] : (fallback !== undefined ? fallback : key);
  }

  function applyLang() {
    // 翻译 data-i18n 元素
    document.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      const translated = t(key);
      if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
        el.placeholder = translated;
      } else {
        el.textContent = translated;
      }
    });
    // 翻译 title
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
      const key = el.getAttribute('data-i18n-title');
      el.title = t(key);
    });
    // 翻译 placeholder
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
      const key = el.getAttribute('data-i18n-placeholder');
      el.placeholder = t(key);
    });
    // 翻译 option 标签
    document.querySelectorAll('option[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      el.textContent = t(key);
    });
    // 更新 lang 属性
    document.documentElement.setAttribute('lang', currentLang === 'zh' ? 'zh-CN' : 'en');
  }

  function initLang() {
    const sel = $('#setting-lang');
    if (sel) sel.value = currentLang;
    applyLang();
  }

  function setLang(lang) {
    currentLang = lang;
    localStorage.setItem(STORAGE_LANG, lang);
    applyLang();
    // 重新渲染动态内容
    renderSessionList();
    renderMessages();
  }

  const ENV = {
    isElectron: !!window.nexusDesktop,
    isPyQt6: typeof qt !== 'undefined',
    get isWeb() { return !this.isElectron && !this.isPyQt6; }
  };

  // ═══════════════════════════════════════════════
  // 状态
  // ═══════════════════════════════════════════════

  let sessions = [];
  let activeSessionId = null;
  let isProcessing = false;
  let abortController = null;
  let pyqtBridge = null;
  let pyqtBridgeReady = false;
  let wsConnection = null;

  // Document editor state
  const STORAGE_DOCS = 'nexus_docs_v1';
  let docs = [];
  let activeDocId = null;
  let isDocDrawerOpen = false;

  // ═══════════════════════════════════════════════
  // DOM 快捷引用
  // ═══════════════════════════════════════════════

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  // ═══════════════════════════════════════════════
  // 初始化
  // ═══════════════════════════════════════════════

  function init() {
    initLang();
    initTheme();
    initDocs();
    initPyQtBridge();
    loadSessions();
    ensureWelcomeSession();
    renderSessionList();
    renderMessages();
    bindEvents();
    updateCharCount();
    checkBackendHealth();
    initModelOptions();
    initWebSocket();
  }

  // WebSocket — 实时告警推送
  function initWebSocket() {
    if (ENV.isPyQt6) return; // PyQt6 通过 QWebChannel，不额外建立 WebSocket
    try {
      const wsUrl = 'ws://127.0.0.1:8080/ws';
      wsConnection = new WebSocket(wsUrl);
      wsConnection.onopen = () => { console.log('WebSocket connected'); };
      wsConnection.onmessage = (evt) => {
        try {
          const data = JSON.parse(evt.data);
          if (data.type === 'alert') {
            showAlertToast(data.level, data.title, data.message);
          }
        } catch (e) { /* ignore non-JSON */ }
      };
      wsConnection.onclose = () => {
        wsConnection = null;
        // 5s 后尝试重连
        setTimeout(initWebSocket, 5000);
      };
      wsConnection.onerror = () => {
        if (wsConnection) { wsConnection.close(); }
      };
    } catch (e) {
      console.warn('WebSocket init failed:', e);
    }
  }

  function showAlertToast(level, title, message) {
    const container = document.body;
    const toast = document.createElement('div');
    toast.className = 'alert-toast ' + (level || 'info');
    toast.innerHTML = `
      <div class="alert-toast-header">
        <span class="alert-toast-dot"></span>
        <strong>${escapeHtml(title || 'Alert')}</strong>
        <button class="alert-toast-close" title="Dismiss">×</button>
      </div>
      <div class="alert-toast-body">${escapeHtml(message || '')}</div>
    `;
    toast.querySelector('.alert-toast-close').addEventListener('click', () => {
      toast.style.animation = 'alert-toast-out 0.25s ease forwards';
      setTimeout(() => toast.remove(), 300);
    });
    container.appendChild(toast);
    // 自动消失
    setTimeout(() => {
      if (toast.parentElement) {
        toast.style.animation = 'alert-toast-out 0.25s ease forwards';
        setTimeout(() => toast.remove(), 300);
      }
    }, 8000);
  }

  // PyQt6 QWebChannel 初始化
  function initPyQtBridge() {
    if (!ENV.isPyQt6) return;
    if (typeof QWebChannel === 'undefined') {
      const script = document.createElement('script');
      script.src = 'qrc:///qtwebchannel/qwebchannel.js';
      script.onload = () => {
        new QWebChannel(qt.webChannelTransport, function(channel) {
          pyqtBridge = channel.objects.agentBridge;
          pyqtBridgeReady = true;
        });
      };
      script.onerror = () => {
        console.error('Failed to load QWebChannel');
        pyqtBridgeReady = true; // 避免阻塞
      };
      document.head.appendChild(script);
    } else {
      new QWebChannel(qt.webChannelTransport, function(channel) {
        pyqtBridge = channel.objects.agentBridge;
        pyqtBridgeReady = true;
      });
    }
  }

  // ═══════════════════════════════════════════════
  // 主题
  // ═══════════════════════════════════════════════

  function initTheme() {
    const saved = localStorage.getItem(STORAGE_THEME) || 'dark';
    applyTheme(saved);
    const sel = $('#setting-theme');
    if (sel) sel.value = saved;
  }

  function applyTheme(theme) {
    const root = document.documentElement;
    if (theme === 'system') {
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      root.setAttribute('data-theme', prefersDark ? 'dark' : 'light');
    } else {
      root.setAttribute('data-theme', theme);
    }
    localStorage.setItem(STORAGE_THEME, theme);
  }

  // ═══════════════════════════════════════════════
  // 会话管理
  // ═══════════════════════════════════════════════

  function loadSessions() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) sessions = JSON.parse(raw);
    } catch (e) { sessions = []; }
    if (!Array.isArray(sessions)) sessions = [];
  }

  function saveSessions() {
    try {
      if (sessions.length > MAX_SESSIONS) sessions = sessions.slice(-MAX_SESSIONS);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
    } catch (e) { console.error('saveSessions failed:', e); }
  }

  function createSession(title = t('session.new_chat')) {
    const id = 'ses_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 6);
    const session = { id, title, createdAt: Date.now(), messages: [] };
    sessions.unshift(session);
    saveSessions();
    return session;
  }

  function deleteSession(id) {
    sessions = sessions.filter(s => s.id !== id);
    saveSessions();
    if (activeSessionId === id) {
      activeSessionId = sessions.length > 0 ? sessions[0].id : null;
      if (!activeSessionId) { const s = createSession(); activeSessionId = s.id; }
      renderMessages();
    }
    renderSessionList();
  }

  function ensureWelcomeSession() {
    if (sessions.length === 0) {
      const s = createSession(t('session.welcome'));
      activeSessionId = s.id;
    } else if (!activeSessionId || !sessions.find(s => s.id === activeSessionId)) {
      activeSessionId = sessions[0].id;
    }
  }

  function renameSessionFromFirstMessage(sessionId, text) {
    const session = sessions.find(s => s.id === sessionId);
    if (!session) return;
    if (session.title === t('session.new_chat') || session.title === t('session.welcome')) {
      const t = text.trim().slice(0, 24);
      session.title = t + (text.length > 24 ? '…' : '');
      saveSessions();
      renderSessionList();
    }
  }

  // ═══════════════════════════════════════════════
  // 渲染
  // ═══════════════════════════════════════════════

  function renderSessionList() {
    const list = $('#session-list');
    if (!list) return;
    list.innerHTML = '';
    if (sessions.length === 0) {
      list.innerHTML = '<div class="session-empty">' + t('session.empty') + '</div>';
      return;
    }
    sessions.forEach(s => {
      const el = document.createElement('div');
      el.className = 'session-item' + (s.id === activeSessionId ? ' active' : '');
      el.innerHTML = `
        <span class="session-icon">💬</span>
        <span class="session-title">${escapeHtml(s.title)}</span>
        <span class="session-del" title="删除">×</span>
      `;
      el.addEventListener('click', (e) => {
        if (e.target.classList.contains('session-del')) {
          e.stopPropagation();
          if (confirm(t('session.confirm_delete'))) deleteSession(s.id);
        } else {
          activeSessionId = s.id;
          renderSessionList();
          renderMessages();
          $('#message-input').focus();
        }
      });
      list.appendChild(el);
    });
  }

  function renderMessages() {
    const container = $('#messages');
    if (!container) return;
    const session = sessions.find(s => s.id === activeSessionId);
    if (!session || session.messages.length === 0) {
      container.innerHTML = `
        <div class="welcome-screen">
          <div class="welcome-logo">◈</div>
          <h1 class="welcome-title">NexusAgent</h1>
          <p class="welcome-subtitle">本地优先的个人智能体系统</p>
          <div class="welcome-cards">
            <div class="welcome-card"><div class="card-icon">💡</div><div class="card-title">智能问答</div><div class="card-desc">基于大模型的自然语言理解与生成</div></div>
            <div class="welcome-card"><div class="card-icon">🛡️</div><div class="card-title">隐私保护</div><div class="card-desc">数据本地存储，PII 自动脱敏</div></div>
            <div class="welcome-card"><div class="card-icon">⚡</div><div class="card-title">工具调用</div><div class="card-desc">代码执行、文件分析、网络请求</div></div>
          </div>
        </div>`;
      return;
    }

    container.innerHTML = '';
    session.messages.forEach(m => appendMessageToDOM(m.role, m.text, false));
    scrollToBottom();
  }

  function addMessage(role, text) {
    const session = sessions.find(s => s.id === activeSessionId);
    if (!session) return;
    session.messages.push({ role, text, time: Date.now() });
    saveSessions();
    appendMessageToDOM(role, text, true);
    if (role === 'user') renameSessionFromFirstMessage(activeSessionId, text);
  }

  function appendDiagnosticHTML(html) {
    const container = $('#messages');
    if (!container) return;
    if (container.querySelector('.welcome-screen')) container.innerHTML = '';

    const row = document.createElement('div');
    row.className = 'msg-row agent';
    row.style.animation = 'msg-enter 0.35s cubic-bezier(0.16, 1, 0.3, 1)';
    row.innerHTML = `
      <div class="msg-inner">
        <div class="msg-avatar agent">N</div>
        <div class="msg-content">
          <div class="msg-bubble agent diag-dashboard">${html}</div>
          <div class="msg-meta">${formatTime(new Date())}</div>
        </div>
      </div>`;
    container.appendChild(row);
    scrollToBottom();
  }

  function appendMessageToDOM(role, text, animate = true) {
    const container = $('#messages');
    if (!container) return;
    // 如果有欢迎页，清空
    if (container.querySelector('.welcome-screen')) container.innerHTML = '';

    const row = document.createElement('div');
    row.className = 'msg-row ' + role;
    if (animate) row.style.animation = 'msg-enter 0.35s cubic-bezier(0.16, 1, 0.3, 1)';

    if (role === 'system') {
      row.innerHTML = `<div class="msg-system-inner">${escapeHtml(text)}</div>`;
    } else {
      const avatarText = role === 'user' ? t('avatar.user') : 'N';
      const bubbleHTML = role === 'agent' ? renderMarkdown(text) : escapeHtml(text);
      row.innerHTML = `
        <div class="msg-inner">
          <div class="msg-avatar ${role}">${avatarText}</div>
          <div class="msg-content">
            <div class="msg-bubble ${role}">${bubbleHTML}</div>
            <div class="msg-meta">${formatTime(new Date())}</div>
          </div>
        </div>`;
    }
    container.appendChild(row);
    scrollToBottom();
    attachCodeCopyButtons(row);
  }

  function showTyping() {
    const container = $('#messages');
    if (!container || container.querySelector('.typing-indicator')) return;
    if (container.querySelector('.welcome-screen')) container.innerHTML = '';
    const row = document.createElement('div');
    row.className = 'msg-row agent';
    row.id = 'typing-row';
    row.innerHTML = `
      <div class="msg-inner">
        <div class="msg-avatar agent">N</div>
        <div class="msg-content">
          <div class="msg-bubble agent">
            <div class="typing-indicator"><span></span><span></span><span></span></div>
          </div>
        </div>
      </div>`;
    container.appendChild(row);
    scrollToBottom();
  }

  function hideTyping() {
    const row = $('#typing-row');
    if (row) row.remove();
  }

  function scrollToBottom() {
    const container = $('#messages');
    if (container) container.scrollTop = container.scrollHeight;
  }

  function formatTime(d) {
    return d.getHours().toString().padStart(2, '0') + ':' + d.getMinutes().toString().padStart(2, '0');
  }

  // ═══════════════════════════════════════════════
  // Markdown 渲染
  // ═══════════════════════════════════════════════

  function renderMarkdown(text) {
    if (!text) return '';
    let html = escapeHtml(text);

    // 代码块（带复制按钮和语言标签）
    html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
      const trimmed = code.trimRight();
      const displayLang = (lang || 'text').toLowerCase();
      return `<pre><div class="code-header"><span>${displayLang}</span><button class="code-copy" onclick="copyCode(this)">复制</button></div><code>${escapeHtml(trimmed)}</code></pre>`;
    });

    // 行内代码
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

    // 粗体 / 斜体 / 删除线
    html = html.replace(/\*\*\*([^*]+)\*\*\*/g, '<strong><em>$1</em></strong>');
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
    html = html.replace(/__(.+?)__/g, '<strong>$1</strong>');
    html = html.replace(/_(.+?)_/g, '<em>$1</em>');
    html = html.replace(/~~(.+?)~~/g, '<del>$1</del>');

    // 标题
    html = html.replace(/^#### (.*$)/gim, '<h4>$1</h4>');
    html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
    html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
    html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');

    // 列表
    html = html.replace(/^[\s]*[-*+] (.*$)/gim, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>\n?)+/g, (m) => `<ul>${m}</ul>`);
    html = html.replace(/^[\s]*\d+\. (.*$)/gim, '<li>$1</li>');

    // 链接
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

    // 引用
    html = html.replace(/^> (.*$)/gim, '<blockquote>$1</blockquote>');

    // 换行（保留段落）
    const paragraphs = html.split(/\n\n+/);
    html = paragraphs.map(p => {
      if (p.trim().startsWith('<') && !p.trim().startsWith('<br>')) return p;
      return '<p>' + p.replace(/\n/g, '<br>') + '</p>';
    }).join('\n');

    // 清理标签周围的 <br>
    html = html.replace(/<\/(h[1-4]|ul|ol|li|blockquote|pre|table|tr|td|th)>(?:<br>)+/g, '</$1>');
    html = html.replace(/(?:<br>)+<(h[1-4]|ul|ol|li|blockquote|pre|table|tr|td|th)>/g, '<$1>');
    html = html.replace(/<p><\/p>/g, '');

    return html;
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  window.copyCode = function(btn) {
    const pre = btn.closest('pre');
    const code = pre.querySelector('code');
    if (!code) return;
    const text = code.textContent;
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text).then(() => {
        btn.textContent = t('action.copied');
        setTimeout(() => btn.textContent = t('action.copy'), 2000);
      });
    } else {
      // fallback
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      btn.textContent = t('action.copied');
      setTimeout(() => btn.textContent = t('action.copy'), 2000);
    }
  };

  function attachCodeCopyButtons(container) {
    // 由 onclick 处理，无需额外绑定
  }

  // ═══════════════════════════════════════════════
  // 输入处理
  // ═══════════════════════════════════════════════

  function adjustTextarea() {
    const ta = $('#message-input');
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 200) + 'px';
  }

  function updateCharCount() {
    const ta = $('#message-input');
    const count = ta ? ta.value.length : 0;
    const el = $('#char-count');
    if (el) el.textContent = count + ' / 50000';
    const sendBtn = $('#btn-send');
    if (sendBtn) sendBtn.disabled = count === 0;
  }

  // ═══════════════════════════════════════════════
  // 通信层
  // ═══════════════════════════════════════════════

  let uploadedFileText = '';
  let uploadedFileName = '';

  async function uploadFile(file) {
    const previewEl = $('#upload-preview');
    const filenameEl = previewEl ? previewEl.querySelector('.upload-filename') : null;

    if (!file) return;
    if (file.size > 20 * 1024 * 1024) {
      showAlertToast('warning', t('upload.too_large'), t('upload.size_limit'));
      return;
    }

    if (filenameEl) filenameEl.textContent = t('upload.uploading') + ' ' + file.name;
    if (previewEl) previewEl.classList.remove('hidden');

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch(API_BASE + '/upload', {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (data.ok) {
        uploadedFileText = data.text || '';
        uploadedFileName = data.filename || file.name;
        if (filenameEl) filenameEl.textContent = '📎 ' + uploadedFileName;
        showAlertToast('info', t('upload.converted'), uploadedFileName + ' ' + t('upload.ready'));
      } else {
        uploadedFileText = '';
        uploadedFileName = '';
        if (filenameEl) filenameEl.textContent = '';
        if (previewEl) previewEl.classList.add('hidden');
        showAlertToast('error', t('upload.failed'), data.error || t('error.unknown'));
      }
    } catch (e) {
      uploadedFileText = '';
      uploadedFileName = '';
      if (previewEl) previewEl.classList.add('hidden');
      showAlertToast('error', t('upload.failed'), e.message || t('error.network'));
    }
  }

  function clearUpload() {
    uploadedFileText = '';
    uploadedFileName = '';
    const previewEl = $('#upload-preview');
    const fileInput = $('#file-input');
    if (previewEl) previewEl.classList.add('hidden');
    if (fileInput) fileInput.value = '';
  }

  async function sendMessage() {
    if (isProcessing) return;
    const ta = $('#message-input');
    let text = ta ? ta.value.trim() : '';
    if (!text && !uploadedFileText) return;

    // 如果上传了文件，将文件内容附加到消息中
    if (uploadedFileText) {
      text = text + '\n\n---\n📎 文件内容: ' + uploadedFileName + '\n' + uploadedFileText;
    }

    addMessage('user', text);
    if (ta) { ta.value = ''; ta.style.height = 'auto'; }
    updateCharCount();
    clearUpload();
    renderSessionList();

    isProcessing = true;
    showTyping();
    updateStatus('thinking', t('status.thinking'));

    try {
      if (ENV.isPyQt6) {
        // PyQt6: 通过 QWebChannel 触发后端，结果通过 uiAPI 回调推送
        await waitPyQtBridge();
        if (pyqtBridge && pyqtBridge.sendMessage) {
          pyqtBridge.sendMessage(text);
        } else {
          throw new Error('PyQt6 bridge not ready');
        }
      } else {
        // Electron / Web: 直接调用 HTTP API
        const res = await fetch(API_BASE + '/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text, session: activeSessionId }),
        });
        const data = await res.json();
        hideTyping();
        if (data.ok) {
          addMessage('agent', data.response);
          if (ENV.isElectron && window.nexusDesktop && window.nexusDesktop.notify && !document.hasFocus()) {
            window.nexusDesktop.notify('NexusAgent', '收到新消息');
          }
        } else {
          addMessage('system', t('error.request_failed') + ': ' + (data.error || t('error.unknown')));
        }
        updateStatus('idle', t('status.ready'));
        isProcessing = false;
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        hideTyping();
        addMessage('system', t('error.connection_failed') + ': ' + (err.message || t('error.network')));
        updateStatus('error', t('status.offline'));
      }
      isProcessing = false;
    }
  }

  async function waitPyQtBridge() {
    for (let i = 0; i < 50; i++) {
      if (pyqtBridgeReady) break;
      await new Promise(r => setTimeout(r, 100));
    }
  }

  async function checkBackendHealth() {
    if (ENV.isPyQt6) {
      updateStatus('idle', t('status.ready'));
      return;
    }
    try {
      const res = await fetch(API_BASE + '/health', { method: 'GET' });
      const data = await res.json();
      if (data.ok) {
        updateStatus('idle', t('status.ready'));
        const modelEl = $('#current-model');
        if (modelEl && data.model) modelEl.textContent = data.model;
      } else {
        updateStatus('error', t('status.error'));
      }
    } catch {
      updateStatus('error', t('status.offline'));
    }
  }

  function updateStatus(type, label) {
    const dot = $('#status-dot');
    const modelEl = $('#current-model');
    if (dot) dot.className = 'status-dot ' + type;
    if (label && modelEl) modelEl.title = label;
  }

  // ═══════════════════════════════════════════════
  // 全局 API（供 PyQt6 后端通过 runJavaScript 调用）
  // ═══════════════════════════════════════════════

  window.uiAPI = {
    addAgentMessage(text) {
      hideTyping();
      addMessage('agent', text);
      updateStatus('idle', t('status.ready'));
      isProcessing = false;
    },
    addError(text) {
      hideTyping();
      addMessage('system', t('error.generic') + ': ' + text);
      updateStatus('error', '出错');
      isProcessing = false;
    },
    setStatus(status, text) {
      updateStatus(status, text);
    },
    showToast(text) {
      // 简单的 toast 实现
      const container = $('#messages');
      if (container) {
        const row = document.createElement('div');
        row.className = 'msg-row system';
        row.innerHTML = `<div class="msg-system-inner">${escapeHtml(text)}</div>`;
        container.appendChild(row);
        scrollToBottom();
        setTimeout(() => row.remove(), 4000);
      }
    }
  };

  // ═══════════════════════════════════════════════
  // 设置抽屉
  // ═══════════════════════════════════════════════

  function openDrawer() { $('#settings-drawer').classList.remove('hidden'); }
  function closeDrawer() { $('#settings-drawer').classList.add('hidden'); }

  function initModelOptions() {
    const providerSel = $('#setting-provider');
    const modelSel = $('#setting-model');
    if (!providerSel || !modelSel) return;

    const modelsByProvider = {
      ollama: ['llama3.2', 'qwen2.5', 'deepseek-coder-v2', 'mistral'],
      moonshot: ['moonshot-v1-8k', 'moonshot-v1-32k', 'moonshot-v1-128k'],
      deepseek: ['deepseek-chat', 'deepseek-v4-pro'],
      openai: ['gpt-4o-mini'],
    };

    const ollamaHostSection = $('#section-ollama-host');
    providerSel.addEventListener('change', () => {
      const models = modelsByProvider[providerSel.value] || [];
      modelSel.innerHTML = models.map(m => `<option value="${m}">${m}</option>`).join('');
      if (ollamaHostSection) {
        ollamaHostSection.style.display = providerSel.value === 'ollama' ? '' : 'none';
      }
    });
    // 初始化显示状态
    if (ollamaHostSection) {
      ollamaHostSection.style.display = providerSel.value === 'ollama' ? '' : 'none';
    }
  }

  async function saveConfig() {
    const provider = $('#setting-provider').value;
    const model = $('#setting-model').value;
    const apiKey = $('#setting-apikey').value.trim();
    const statusEl = $('#save-status');
    const ollamaHost = provider === 'ollama' ? ($('#setting-ollama-host')?.value || 'http://localhost:11434') : '';
    const payload = JSON.stringify({ provider, model, api_key: apiKey, ollama_host: ollamaHost });

    if (statusEl) { statusEl.textContent = 'Saving…'; statusEl.className = 'save-status'; }

    try {
      let data;
      if (ENV.isPyQt6) {
        await waitPyQtBridge();
        if (pyqtBridge && pyqtBridge.saveConfig) {
          const result = pyqtBridge.saveConfig(payload);
          data = typeof result === 'string' ? JSON.parse(result) : result;
        } else {
          throw new Error('PyQt6 bridge not ready');
        }
      } else {
        const res = await fetch(API_BASE + '/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: payload,
        });
        data = await res.json();
      }

      if (data.ok) {
        if (statusEl) { statusEl.textContent = '✓ ' + t('settings.saved'); statusEl.className = 'save-status ok'; }
        const modelEl = $('#current-model');
        if (modelEl) modelEl.textContent = model;
        const apiInput = $('#setting-apikey');
        if (apiInput) apiInput.value = '';
      } else {
        if (statusEl) { statusEl.textContent = '✗ ' + (data.error || t('settings.save_failed')); statusEl.className = 'save-status err'; }
      }
    } catch (e) {
      if (statusEl) { statusEl.textContent = '✗ ' + t('error.generic') + ': ' + e.message; statusEl.className = 'save-status err'; }
    }
  }

  // ═══════════════════════════════════════════════
  // Diagnostics
  // ═══════════════════════════════════════════════

  // Auto-refresh state
  const AUTO_REFRESH_INTERVAL = 30000; // 30s
  let autoRefreshEnabled = localStorage.getItem('nexus_diag_autorefresh') !== 'false';
  let autoRefreshTimer = null;
  let lastDiagnosticType = '';

  function openDiagnosticsDrawer() {
    $('#diagnostics-drawer').classList.remove('hidden');
    startAutoRefresh();
  }
  function closeDiagnosticsDrawer() {
    $('#diagnostics-drawer').classList.add('hidden');
    stopAutoRefresh();
  }

  function startAutoRefresh() {
    stopAutoRefresh();
    if (!autoRefreshEnabled) return;
    autoRefreshTimer = setInterval(() => {
      if (lastDiagnosticType) {
        refreshCurrentDiagnostic(lastDiagnosticType);
      }
    }, AUTO_REFRESH_INTERVAL);
  }
  function stopAutoRefresh() {
    if (autoRefreshTimer) { clearInterval(autoRefreshTimer); autoRefreshTimer = null; }
  }

  function toggleAutoRefresh() {
    autoRefreshEnabled = !autoRefreshEnabled;
    localStorage.setItem('nexus_diag_autorefresh', String(autoRefreshEnabled));
    const cb = $('#diag-autorefresh-toggle');
    if (cb) cb.checked = autoRefreshEnabled;
    if (autoRefreshEnabled) startAutoRefresh();
    else stopAutoRefresh();
  }

  async function refreshCurrentDiagnostic(type) {
    // Silent refresh — no button state changes
    let endpoint = '';
    let method = 'GET';
    let body = null;
    switch (type) {
      case 'health': endpoint = '/diagnostics/health/full'; break;
      case 'connectivity': endpoint = '/diagnostics/connectivity'; break;
      case 'modules': endpoint = '/diagnostics/modules'; break;
      case 'audit': endpoint = '/diagnostics/audit'; break;
      case 'ux': endpoint = '/diagnostics/ux?theme=dark&model=web'; break;
      default: return;
    }
    try {
      const opts = { method };
      if (body) { opts.headers = { 'Content-Type': 'application/json' }; opts.body = body; }
      const res = await fetch(API_BASE + endpoint, opts);
      const data = await res.json();
      if (data.ok) renderDiagnosticResult(type, data);
    } catch (e) { /* silent fail on auto-refresh */ }
  }

  async function runDiagnostic(type, btn) {
    lastDiagnosticType = type;
    if (btn && btn.disabled) return;
    const originalText = btn ? btn.textContent : 'Run';
    if (btn) { btn.textContent = 'Running…'; btn.disabled = true; }

    let endpoint = '';
    let method = 'GET';
    let body = null;

    switch (type) {
      case 'health': endpoint = '/diagnostics/health/full'; break;
      case 'connectivity': endpoint = '/diagnostics/connectivity'; break;
      case 'modules': endpoint = '/diagnostics/modules'; break;
      case 'audit': endpoint = '/diagnostics/audit'; break;
      case 'ux': {
        const theme = document.documentElement.getAttribute('data-theme') || 'dark';
        const model = $('#current-model') ? $('#current-model').textContent : '';
        endpoint = '/diagnostics/ux?theme=' + encodeURIComponent(theme) + '&model=' + encodeURIComponent(model);
        break;
      }
      case 'design': {
        const baseline = $('#diag-design-baseline').value.trim();
        const current = $('#diag-design-current').value.trim();
        if (!baseline || !current) {
          btn.textContent = originalText; btn.disabled = false;
          addMessage('system', 'Design Diff: both baseline and current are required.');
          return;
        }
        endpoint = '/diagnostics/compare/design';
        method = 'POST';
        body = JSON.stringify({ baseline, current });
        break;
      }
      case 'competitor': {
        const name = $('#diag-competitor-name').value.trim() || 'Competitor';
        const ours = $('#diag-competitor-ours').value.trim().split('\n').filter(Boolean);
        const theirs = $('#diag-competitor-theirs').value.trim().split('\n').filter(Boolean);
        if (!ours.length || !theirs.length) {
          btn.textContent = originalText; btn.disabled = false;
          addMessage('system', 'Competitor Analysis: both feature lists are required.');
          return;
        }
        endpoint = '/diagnostics/compare/competitor';
        method = 'POST';
        body = JSON.stringify({ competitor_name: name, our_features: ours, competitor_features: theirs });
        break;
      }
    }

    try {
      const opts = { method, headers: {} };
      if (body) { opts.headers['Content-Type'] = 'application/json'; opts.body = body; }
      const res = await fetch(API_BASE + endpoint, opts);
      const data = await res.json();
      renderDiagnosticResult(type, data);
    } catch (e) {
      addMessage('system', 'Diagnostic failed: ' + (e.message || t('error.network')));
    } finally {
      if (btn) { btn.textContent = originalText; btn.disabled = false; }
    }
  }

  function renderDiagnosticResult(type, data) {
    if (!data.ok) {
      addMessage('system', 'Diagnostic error: ' + (data.error || t('error.unknown')));
      return;
    }
    let html = '';
    switch (type) {
      case 'health': {
        const m = data.metrics || {};
        const overall = data.overall_healthy;
        html += `<h3>🏥 Health Dashboard</h3>`;
        html += `<div class="diag-summary-row">`;
        html += `<div class="diag-status-card"><span class="label">Status</span><span class="value" style="color:${overall ? 'var(--accent)' : 'var(--danger)'}">${overall ? 'Healthy' : 'Issues'}</span><span class="sub">${new Date(data.timestamp * 1000).toLocaleTimeString()}</span></div>`;
        html += `<div class="diag-status-card"><span class="label">Sessions</span><span class="value">${m.active_sessions || 0}</span></div>`;
        html += `<div class="diag-status-card"><span class="label">Avg Latency</span><span class="value">${(m.avg_latency_ms || 0).toFixed(1)}<span style="font-size:11px;color:var(--text-tertiary)">ms</span></span></div>`;
        html += `<div class="diag-status-card"><span class="label">Security</span><span class="value">${m.security_interceptions || 0}</span><span class="sub">interceptions</span></div>`;
        html += `</div>`;
        html += `<h3>Metrics (1h)</h3>`;
        html += `<div class="diag-metrics-grid">`;
        html += `<div class="diag-metric"><div class="k">Requests</div><div class="v">${m.requests_total || 0}</div></div>`;
        html += `<div class="diag-metric"><div class="k">Success</div><div class="v" style="color:var(--accent)">${m.requests_success || 0}</div></div>`;
        html += `<div class="diag-metric"><div class="k">Errors</div><div class="v" style="color:var(--danger)">${m.requests_error || 0}</div></div>`;
        html += `<div class="diag-metric"><div class="k">Tokens</div><div class="v">${(m.token_usage_total || 0).toLocaleString()}</div></div>`;
        html += `</div>`;
        const backends = Object.entries(data.backends || {});
        if (backends.length) {
          html += `<h3>Backends</h3><table class="diag-table"><thead><tr><th>Name</th><th>Status</th><th>Error Rate</th><th>p99 Latency</th></tr></thead><tbody>`;
          for (const [name, info] of backends) {
            const badge = info.is_healthy ? '<span class="diag-badge ok">Healthy</span>' : '<span class="diag-badge err">Unhealthy</span>';
            html += `<tr><td>${escapeHtml(name)}</td><td>${badge}</td><td>${((info.error_rate || 0) * 100).toFixed(1)}%</td><td>${info.p99_latency_ms || 0}ms</td></tr>`;
          }
          html += `</tbody></table>`;
        }
        html += `<h3>Security</h3>`;
        const sec = data.security || {};
        for (const [k, v] of Object.entries(sec)) {
          const isObj = v && typeof v === 'object';
          const avail = isObj ? (v.available !== false) : (v !== 'unavailable');
          const badge = avail ? '<span class="diag-badge ok">OK</span>' : '<span class="diag-badge err">Fail</span>';
          html += `<div class="diag-probe">${badge}<span class="name">${escapeHtml(k)}</span><span class="detail">${isObj ? JSON.stringify(v).slice(0, 80) : escapeHtml(String(v))}</span></div>`;
        }
        const exec = data.execution || {};
        if (exec.total_tasks !== undefined) {
          html += `<h3>Execution</h3>`;
          html += `<div class="diag-metrics-grid">`;
          for (const [k, v] of Object.entries(exec.by_status || {})) {
            html += `<div class="diag-metric"><div class="k">${escapeHtml(k)}</div><div class="v">${v}</div></div>`;
          }
          html += `</div>`;
        }
        const mem = data.memory || {};
        if (mem.total !== undefined || mem.db_file_size_mb !== undefined) {
          html += `<h3>Memory</h3>`;
          html += `<div class="diag-metrics-grid">`;
          html += `<div class="diag-metric"><div class="k">Total</div><div class="v">${mem.total || 0}</div></div>`;
          html += `<div class="diag-metric"><div class="k">DB Size</div><div class="v">${mem.db_file_size_mb || 0}MB</div></div>`;
          html += `<div class="diag-metric"><div class="k">Core Blocks</div><div class="v">${mem.core_blocks || 0}</div></div>`;
          html += `</div>`;
        }
        const sys = data.system || {};
        if (sys.memory) {
          html += `<h3>System</h3>`;
          html += `<div class="diag-metrics-grid">`;
          html += `<div class="diag-metric"><div class="k">Memory Used</div><div class="v">${sys.memory.percent_used || 0}%</div></div>`;
          html += `<div class="diag-metric"><div class="k">Disk Used</div><div class="v">${sys.disk && sys.disk.percent_used ? sys.disk.percent_used + '%' : 'N/A'}</div></div>`;
          html += `<div class="diag-metric"><div class="k">CPU</div><div class="v">${sys.cpu_percent !== undefined ? sys.cpu_percent + '%' : 'N/A'}</div></div>`;
          html += `</div>`;
        }
        break;
      }
      case 'connectivity': {
        html += `<h3>🔗 Connectivity Test</h3>`;
        html += `<div class="diag-summary-row">`;
        html += `<div class="diag-status-card"><span class="label">Overall</span><span class="value" style="color:${data.ok ? 'var(--accent)' : 'var(--danger)'}">${data.ok ? 'OK' : 'Fail'}</span></div>`;
        html += `</div>`;
        html += `<h3>Probes</h3>`;
        const probes = data.probes || {};
        for (const [name, info] of Object.entries(probes)) {
          const ok = info.status === 'ok';
          html += `<div class="diag-probe"><div class="dot ${ok ? 'ok' : 'err'}"></div><span class="name">${escapeHtml(name)}</span><span class="detail">${ok ? 'Connected' : escapeHtml(info.error || 'Failed')}</span></div>`;
        }
        html += `<h3>Tool Registry</h3>`;
        const tr = data.tool_registry || {};
        html += `<div class="diag-metrics-grid">`;
        html += `<div class="diag-metric"><div class="k">Total</div><div class="v">${tr.total || 0}</div></div>`;
        html += `<div class="diag-metric"><div class="k">Enabled</div><div class="v">${tr.enabled || 0}</div></div>`;
        html += `</div>`;
        html += `<h3>Modules</h3><table class="diag-table"><thead><tr><th>Module</th><th>Status</th></tr></thead><tbody>`;
        for (const [name, info] of Object.entries(data.modules || {})) {
          const badge = info.status === 'ok' ? '<span class="diag-badge ok">OK</span>' : '<span class="diag-badge err">Fail</span>';
          html += `<tr><td>${escapeHtml(name)}</td><td>${badge}</td></tr>`;
        }
        html += `</tbody></table>`;
        break;
      }
      case 'modules': {
        const pct = data.total ? Math.round((data.healthy / data.total) * 100) : 0;
        html += `<h3>📦 Module Status</h3>`;
        html += `<div class="diag-summary-row">`;
        html += `<div class="diag-status-card"><span class="label">Healthy</span><span class="value">${data.healthy}/${data.total}</span></div>`;
        html += `<div class="diag-status-card" style="flex:2"><span class="label">Health</span><div class="diag-progress ${pct < 80 ? 'warn' : ''}"><div style="width:${pct}%"></div></div><span class="sub">${pct}%</span></div>`;
        html += `</div>`;
        html += `<table class="diag-table"><thead><tr><th>Module</th><th>Status</th><th>Deep Check</th></tr></thead><tbody>`;
        for (const m of data.modules || []) {
          const badge = m.status === 'ok' ? '<span class="diag-badge ok">OK</span>' : '<span class="diag-badge err">Fail</span>';
          let deep = '-';
          if (m.deep) {
            if (m.deep.error) deep = `<span style="color:var(--danger)">${escapeHtml(m.deep.error.slice(0, 40))}</span>`;
            else if (m.deep.total_memories !== undefined) deep = `${m.deep.total_memories} memories, ${m.deep.core_blocks} blocks`;
            else if (m.deep.total_tasks !== undefined) deep = `${m.deep.total_tasks} tasks`;
            else if (m.deep.total_tools !== undefined) deep = `${m.deep.total_tools} tools`;
            else if (m.deep.debug !== undefined) deep = `debug=${m.deep.debug}, provider=${escapeHtml(m.deep.default_provider || '')}`;
            else if (m.deep.import_check) deep = 'Import OK';
            else deep = JSON.stringify(m.deep).slice(0, 60);
          }
          html += `<tr><td>${escapeHtml(m.name)}</td><td>${badge}</td><td>${deep}</td></tr>`;
        }
        html += `</tbody></table>`;
        break;
      }
      case 'audit': {
        html += `<h3>📋 Audit Viewer</h3>`;
        html += `<div class="diag-summary-row">`;
        html += `<div class="diag-status-card"><span class="label">Interceptions</span><span class="value">${data.summary.security_interceptions_total || 0}</span></div>`;
        html += `<div class="diag-status-card"><span class="label">Traces</span><span class="value">${data.summary.recent_traces_count || 0}</span></div>`;
        html += `<div class="diag-status-card"><span class="label">Audit Entries</span><span class="value">${data.summary.audit_entries_loaded || 0}</span></div>`;
        html += `</div>`;
        if (data.audit && data.audit.length) {
          html += `<h3>Audit Log</h3><table class="diag-table"><thead><tr><th>Time</th><th>Level</th><th>Event</th><th>Detail</th></tr></thead><tbody>`;
          for (const e of data.audit.slice(0, 20)) {
            if (e.error) { html += `<tr><td colspan="4" style="color:var(--danger)">${escapeHtml(e.error)}</td></tr>`; continue; }
            html += `<tr><td>${escapeHtml(e.timestamp || '')}</td><td><span class="diag-badge ${(e.level === 'ERROR' ? 'err' : e.level === 'WARN' ? 'warn' : 'ok')}">${escapeHtml(e.level || 'INFO')}</span></td><td>${escapeHtml(e.event || '')}</td><td>${escapeHtml(e.detail || '').slice(0, 60)}</td></tr>`;
          }
          html += `</tbody></table>`;
        }
        if (data.traces && data.traces.length) {
          html += `<h3>Recent Traces</h3><table class="diag-table"><thead><tr><th>Trace ID</th><th>Operation</th><th>Status</th></tr></thead><tbody>`;
          for (const t of data.traces.slice(0, 10)) {
            html += `<tr><td><code>${escapeHtml(t.trace_id || '').slice(0, 16)}</code></td><td>${escapeHtml(t.operation || '')}</td><td><span class="diag-badge ${(t.status === 'ok' || t.status === 'completed' ? 'ok' : 'warn')}">${escapeHtml(t.status || '?')}</span></td></tr>`;
          }
          html += `</tbody></table>`;
        }
        break;
      }
      case 'ux': {
        const score = data.score || 0;
        html += `<h3>✨ UX Advisor</h3>`;
        html += `<div class="diag-summary-row">`;
        html += `<div class="diag-status-card"><span class="label">Score</span><span class="value" style="color:${score >= 80 ? 'var(--accent)' : score >= 50 ? 'var(--warning)' : 'var(--danger)'}">${score}</span><span class="sub">/ 100</span></div>`;
        html += `<div class="diag-status-card" style="flex:2"><span class="label">Health</span><div class="diag-progress ${score < 50 ? 'err' : score < 80 ? 'warn' : ''}"><div style="width:${score}%"></div></div></div>`;
        html += `</div>`;
        if (data.recommendations && data.recommendations.length) {
          html += `<div class="diag-recommendations"><strong style="font-size:12px;color:var(--text-primary)">Recommendations</strong><ul style="margin:6px 0 0;padding:0;list-style:none">`;
          for (const r of data.recommendations) {
            html += `<li>${escapeHtml(r)}</li>`;
          }
          html += `</ul></div>`;
        }
        html += `<h3>Checks</h3><div class="diag-metrics-grid">`;
        for (const [k, v] of Object.entries(data.checks || {})) {
          html += `<div class="diag-metric"><div class="k">${escapeHtml(k)}</div><div class="v" style="font-size:12px">${escapeHtml(String(v))}</div></div>`;
        }
        html += `</div>`;
        break;
      }
      case 'design': {
        const a = data.analysis || {};
        html += `<h3>🎨 Design Diff</h3>`;
        html += `<div class="diag-summary-row">`;
        html += `<div class="diag-status-card"><span class="label">Baseline</span><span class="value">${a.baseline_lines || 0}</span><span class="sub">lines</span></div>`;
        html += `<div class="diag-status-card"><span class="label">Current</span><span class="value">${a.current_lines || 0}</span><span class="sub">lines</span></div>`;
        html += `<div class="diag-status-card"><span class="label">Added</span><span class="value" style="color:var(--accent)">+${a.added_count || 0}</span></div>`;
        html += `<div class="diag-status-card"><span class="label">Removed</span><span class="value" style="color:var(--danger)">-${a.removed_count || 0}</span></div>`;
        html += `</div>`;
        if (a.added && a.added.length) {
          html += `<h3>Added Lines</h3><pre style="background:var(--bg-base);border:1px solid var(--border-subtle);border-radius:var(--radius-sm);padding:10px;font-size:12px;overflow-x:auto"><code>${escapeHtml(a.added.join('\n'))}</code></pre>`;
        }
        if (a.removed && a.removed.length) {
          html += `<h3>Removed Lines</h3><pre style="background:var(--bg-base);border:1px solid var(--border-subtle);border-radius:var(--radius-sm);padding:10px;font-size:12px;overflow-x:auto"><code>${escapeHtml(a.removed.join('\n'))}</code></pre>`;
        }
        if (data.recommendations && data.recommendations.length) {
          html += `<div class="diag-recommendations"><strong style="font-size:12px;color:var(--text-primary)">Recommendations</strong><ul style="margin:6px 0 0;padding:0;list-style:none">`;
          for (const r of data.recommendations) { html += `<li>${escapeHtml(r)}</li>`; }
          html += `</ul></div>`;
        }
        break;
      }
      case 'competitor': {
        const a = data.analysis || {};
        html += `<h3>🏆 Competitor Analysis: ${escapeHtml(data.competitor || '')}</h3>`;
        html += `<div class="diag-summary-row">`;
        html += `<div class="diag-status-card"><span class="label">Ours</span><span class="value">${a.our_feature_count || 0}</span></div>`;
        html += `<div class="diag-status-card"><span class="label">Theirs</span><span class="value">${a.competitor_feature_count || 0}</span></div>`;
        html += `<div class="diag-status-card"><span class="label">Common</span><span class="value">${(a.common_features || []).length}</span></div>`;
        html += `<div class="diag-status-card"><span class="label">Gaps</span><span class="value" style="color:var(--danger)">${(a.gaps || []).length}</span></div>`;
        html += `</div>`;
        if (a.gaps && a.gaps.length) {
          html += `<h3>Gaps (${a.gaps.length})</h3><table class="diag-table"><tbody>`;
          for (const g of a.gaps) { html += `<tr><td>${escapeHtml(g)}</td></tr>`; }
          html += `</tbody></table>`;
        }
        if (a.advantages && a.advantages.length) {
          html += `<h3>Advantages (${a.advantages.length})</h3><table class="diag-table"><tbody>`;
          for (const g of a.advantages) { html += `<tr><td>${escapeHtml(g)}</td></tr>`; }
          html += `</tbody></table>`;
        }
        if (data.recommendations && data.recommendations.length) {
          html += `<div class="diag-recommendations"><strong style="font-size:12px;color:var(--text-primary)">Recommendations</strong><ul style="margin:6px 0 0;padding:0;list-style:none">`;
          for (const r of data.recommendations) { html += `<li>${escapeHtml(r)}</li>`; }
          html += `</ul></div>`;
        }
        break;
      }
    }
    appendDiagnosticHTML(html);
  }

  // ═══════════════════════════════════════════════
  // History — 诊断历史趋势
  // ═══════════════════════════════════════════════

  async function loadHistory() {
    const category = $('#diag-history-category').value;
    const hours = $('#diag-history-hours').value;
    const chartEl = $('#diag-history-chart');
    const tableEl = $('#diag-history-table');
    if (chartEl) chartEl.innerHTML = '<div style="padding:20px;color:var(--text-muted)">Loading…</div>';

    try {
      const res = await fetch(`${API_BASE}/api/diagnostics/history?category=${encodeURIComponent(category)}&hours=${encodeURIComponent(hours)}`);
      const data = await res.json();
      if (!data.ok) {
        if (chartEl) chartEl.innerHTML = '<div style="padding:20px;color:var(--danger)">Failed to load history</div>';
        return;
      }
      renderHistoryChart(data.points || [], category);
      renderHistoryTable(data.points || []);
    } catch (e) {
      if (chartEl) chartEl.innerHTML = '<div style="padding:20px;color:var(--danger)">Error: ' + escapeHtml(e.message) + '</div>';
    }
  }

  function renderHistoryChart(points, category) {
    const el = $('#diag-history-chart');
    if (!el) return;
    if (!points.length) {
      el.innerHTML = '<div style="padding:20px;color:var(--text-muted)">No data for selected range</div>';
      return;
    }

    // Extract metric per category
    function getMetric(p) {
      const d = p.data || {};
      switch (category) {
        case 'health': return d.overall_healthy ? 100 : 0;
        case 'connectivity': {
          const t = d.total || 1;
          const h = d.healthy || 0;
          return Math.round((h / t) * 100);
        }
        case 'modules': {
          const t = d.total || 1;
          const h = d.healthy || 0;
          return Math.round((h / t) * 100);
        }
        case 'ux': return d.score || 0;
        default: return 0;
      }
    }

    // Downsample to max 24 bars
    const maxBars = 24;
    let display = points;
    if (points.length > maxBars) {
      const step = Math.ceil(points.length / maxBars);
      display = [];
      for (let i = 0; i < points.length; i += step) {
        const chunk = points.slice(i, i + step);
        const avg = chunk.reduce((s, p) => s + getMetric(p), 0) / chunk.length;
        display.push({ timestamp: chunk[chunk.length - 1].timestamp, value: Math.round(avg) });
      }
    } else {
      display = points.map(p => ({ timestamp: p.timestamp, value: getMetric(p) }));
    }

    let html = '<div class="diag-history-chart-inner">';
    for (const pt of display) {
      const pct = Math.max(0, Math.min(100, pt.value));
      const color = pct >= 80 ? 'var(--accent)' : pct >= 50 ? 'var(--warning)' : 'var(--danger)';
      const timeStr = new Date(pt.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      html += `<div class="diag-history-bar-wrap" title="${timeStr}: ${pt.value}%">`;
      html += `<div class="diag-history-bar" style="height:${pct}%;background:${color}"></div>`;
      html += `</div>`;
    }
    html += '</div>';
    html += '<div class="diag-history-xaxis">';
    const firstTime = new Date(display[0].timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const lastTime = new Date(display[display.length - 1].timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    html += `<span>${firstTime}</span><span>${lastTime}</span>`;
    html += '</div>';
    el.innerHTML = html;
  }

  function renderHistoryTable(points) {
    const el = $('#diag-history-table');
    if (!el) return;
    if (!points.length) { el.innerHTML = ''; return; }
    const recent = points.slice(-10).reverse();
    let html = '<table class="diag-table"><thead><tr><th>Time</th><th>Alerts</th><th>Preview</th></tr></thead><tbody>';
    for (const p of recent) {
      const timeStr = new Date(p.timestamp * 1000).toLocaleString();
      const alertBadge = p.alert_count > 0 ? `<span class="diag-badge err">${p.alert_count}</span>` : '<span class="diag-badge ok">0</span>';
      const preview = JSON.stringify(p.data).slice(0, 60);
      html += `<tr><td>${timeStr}</td><td>${alertBadge}</td><td><code>${escapeHtml(preview)}</code></td></tr>`;
    }
    html += '</tbody></table>';
    el.innerHTML = html;
  }

  // ═══════════════════════════════════════════════
  // Alerts — 告警历史
  // ═══════════════════════════════════════════════

  async function loadAlerts() {
    const levelBtn = document.querySelector('.diag-alert-filters .active');
    const level = levelBtn ? levelBtn.getAttribute('data-alert-level') : '';
    const hours = $('#diag-alert-hours').value;
    const el = $('#diag-alerts-table');
    if (el) el.innerHTML = '<div style="padding:12px;color:var(--text-muted)">Loading…</div>';

    try {
      const url = `${API_BASE}/api/diagnostics/alerts?hours=${encodeURIComponent(hours)}${level ? '&level='+encodeURIComponent(level) : ''}`;
      const res = await fetch(url);
      const data = await res.json();
      if (!data.ok) {
        if (el) el.innerHTML = '<div style="padding:12px;color:var(--danger)">Failed to load alerts</div>';
        return;
      }
      renderAlerts(data.alerts || []);
      updateAlertBadge(data.unacknowledged_count || 0);
    } catch (e) {
      if (el) el.innerHTML = '<div style="padding:12px;color:var(--danger)">Error: ' + escapeHtml(e.message) + '</div>';
    }
  }

  function renderAlerts(alerts) {
    const el = $('#diag-alerts-table');
    if (!el) return;
    if (!alerts.length) {
      el.innerHTML = '<div style="padding:12px;color:var(--text-muted)">No alerts for selected range</div>';
      return;
    }
    let html = '<table class="diag-table"><thead><tr><th>Time</th><th>Level</th><th>Title</th><th>Source</th><th></th></tr></thead><tbody>';
    for (const a of alerts) {
      const timeStr = new Date(a.timestamp * 1000).toLocaleString();
      const levelColor = a.level === 'critical' || a.level === 'error' ? 'err' : a.level === 'warning' ? 'warn' : 'ok';
      const ackBtn = a.acknowledged
        ? '<span style="font-size:11px;color:var(--text-muted)">Acked</span>'
        : `<button class="btn-diag-run" style="font-size:11px;padding:2px 8px" onclick="ackAlert('${a.id}')">Ack</button>`;
      html += `<tr><td>${timeStr}</td><td><span class="diag-badge ${levelColor}">${escapeHtml(a.level)}</span></td><td>${escapeHtml(a.title)}</td><td>${escapeHtml(a.source)}</td><td>${ackBtn}</td></tr>`;
    }
    html += '</tbody></table>';
    el.innerHTML = html;
  }

  async function ackAlert(alertId) {
    try {
      const res = await fetch(`${API_BASE}/api/diagnostics/alerts/ack`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ alert_id: alertId }),
      });
      const data = await res.json();
      if (data.ok) loadAlerts();
    } catch (e) {}
  }

  function updateAlertBadge(count) {
    const btn = $('#btn-diagnostics');
    if (!btn) return;
    const existing = btn.querySelector('.alert-badge');
    if (existing) existing.remove();
    if (count > 0) {
      const badge = document.createElement('span');
      badge.className = 'alert-badge';
      badge.textContent = String(count);
      btn.appendChild(badge);
    }
  }

  // ═══════════════════════════════════════════════
  // Export — 诊断报告导出
  // ═══════════════════════════════════════════════

  async function exportReport() {
    const format = $('#diag-export-format').value;
    const btn = $('#btn-export-report');
    if (btn) { btn.textContent = 'Exporting…'; btn.disabled = true; }

    try {
      if (format === 'markdown') {
        const res = await fetch(`${API_BASE}/api/diagnostics/export`);
        const data = await res.json();
        if (data.ok && data.markdown) {
          downloadFile('nexusagent-diagnostic-report.md', data.markdown, 'text/markdown');
        }
      } else {
        const endpoints = ['health/full', 'connectivity', 'modules', 'audit', 'ux'];
        const results = {};
        for (const ep of endpoints) {
          const r = await fetch(`${API_BASE}/api/diagnostics/${ep}`);
          results[ep] = await r.json();
        }
        downloadFile('nexusagent-diagnostic-report.json', JSON.stringify(results, null, 2), 'application/json');
      }
    } catch (e) {
      addMessage('system', 'Export failed: ' + (e.message || t('error.network')));
    } finally {
      if (btn) { btn.textContent = 'Export'; btn.disabled = false; }
    }
  }

  function downloadFile(filename, content, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 1000);
  }

  // ═══════════════════════════════════════════════
  // Diagnostics Config — 诊断配置
  // ═══════════════════════════════════════════════

  async function loadDiagConfig() {
    try {
      const res = await fetch(`${API_BASE}/api/diagnostics/config`);
      const data = await res.json();
      if (!data.ok || !data.config) return;
      const c = data.config;
      const setVal = (id, val) => { const el = $(id); if (el) el.value = String(val); };
      setVal('#diag-cfg-interval', c.scheduler_interval_seconds);
      setVal('#diag-cfg-latency-warn', c.latency_warning_ms);
      setVal('#diag-cfg-latency-crit', c.latency_critical_ms);
      setVal('#diag-cfg-err-warn', c.error_rate_warning);
      setVal('#diag-cfg-err-crit', c.error_rate_critical);
      setVal('#diag-cfg-history-days', c.history_keep_days);
      setVal('#diag-cfg-alerts-days', c.alerts_keep_days);
    } catch (e) {}
  }

  async function saveDiagConfig() {
    const getVal = (id) => { const el = $(id); return el ? parseFloat(el.value) : 0; };
    const payload = {
      scheduler_interval_seconds: getVal('#diag-cfg-interval'),
      latency_warning_ms: getVal('#diag-cfg-latency-warn'),
      latency_critical_ms: getVal('#diag-cfg-latency-crit'),
      error_rate_warning: getVal('#diag-cfg-err-warn'),
      error_rate_critical: getVal('#diag-cfg-err-crit'),
      history_keep_days: getVal('#diag-cfg-history-days'),
      alerts_keep_days: getVal('#diag-cfg-alerts-days'),
    };
    try {
      const res = await fetch(`${API_BASE}/api/diagnostics/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (data.ok) {
        const status = $('#save-status');
        if (status) { status.textContent = '✓ ' + t('settings.saved'); status.className = 'save-status ok'; }
      }
    } catch (e) {}
  }

  // ═══════════════════════════════════════════════
  // 事件绑定
  // ═══════════════════════════════════════════════

  function bindEvents() {
    const ta = $('#message-input');

    // 发送
    $('#btn-send').addEventListener('click', sendMessage);
    if (ta) {
      ta.addEventListener('input', () => { adjustTextarea(); updateCharCount(); });
      ta.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
      });
    }

    // 文件上传
    const btnUpload = $('#btn-upload');
    const fileInput = $('#file-input');
    const btnClearUpload = $('#btn-clear-upload');
    if (btnUpload && fileInput) {
      btnUpload.addEventListener('click', () => fileInput.click());
      fileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) uploadFile(file);
      });
    }
    if (btnClearUpload) {
      btnClearUpload.addEventListener('click', clearUpload);
    }

    // 新对话
    $('#btn-new-chat').addEventListener('click', () => {
      const s = createSession();
      activeSessionId = s.id;
      renderSessionList();
      renderMessages();
      if (ta) ta.focus();
    });

    // 清空当前对话
    $('#btn-clear-chat').addEventListener('click', () => {
      const session = sessions.find(s => s.id === activeSessionId);
      if (session) {
        session.messages = [];
        saveSessions();
        renderMessages();
      }
    });

    // 侧边栏折叠
    $('#btn-toggle-sidebar').addEventListener('click', () => {
      $('#sidebar').classList.toggle('collapsed');
    });

    // 设置抽屉
    $('#btn-settings').addEventListener('click', openDrawer);
    $('#btn-close-drawer').addEventListener('click', closeDrawer);
    $('.drawer-backdrop').addEventListener('click', closeDrawer);

    // Diagnostics 抽屉
    $('#btn-diagnostics').addEventListener('click', openDiagnosticsDrawer);
    $('#btn-close-diagnostics').addEventListener('click', closeDiagnosticsDrawer);
    $('#diagnostics-drawer .drawer-backdrop').addEventListener('click', closeDiagnosticsDrawer);

    // Diagnostic cards
    $$('.diag-card .btn-diag-run').forEach(btn => {
      const card = btn.closest('.diag-card');
      const type = card ? card.getAttribute('data-diag') : '';
      btn.addEventListener('click', () => runDiagnostic(type, btn));
    });

    // Diagnostic forms
    $$('.diag-form .btn-diag-run').forEach(btn => {
      const type = btn.getAttribute('data-diag');
      btn.addEventListener('click', () => runDiagnostic(type, btn));
    });

    // History load button
    const histBtn = $('#btn-load-history');
    if (histBtn) histBtn.addEventListener('click', loadHistory);

    // Auto-refresh toggle
    const arToggle = $('#diag-autorefresh-toggle');
    if (arToggle) {
      arToggle.checked = autoRefreshEnabled;
      arToggle.addEventListener('change', toggleAutoRefresh);
    }

    // Alerts
    const alertsBtn = $('#btn-load-alerts');
    if (alertsBtn) alertsBtn.addEventListener('click', loadAlerts);
    $$('.diag-alert-filters .diag-filter-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        $$('.diag-alert-filters .diag-filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        loadAlerts();
      });
    });

    // Export
    const exportBtn = $('#btn-export-report');
    if (exportBtn) exportBtn.addEventListener('click', exportReport);

    // Diagnostics config
    const saveCfgBtn = $('#btn-save-config');
    if (saveCfgBtn) {
      // Wrap existing saveConfig to also save diag config
      const origSave = saveCfgBtn.onclick;
      saveCfgBtn.addEventListener('click', () => {
        saveDiagConfig();
      });
    }
    // Load diag config when settings drawer opens
    $('#btn-settings').addEventListener('click', loadDiagConfig);

    // API Key 显示/隐藏
    $('#btn-toggle-key').addEventListener('click', () => {
      const input = $('#setting-apikey');
      if (input) input.type = input.type === 'password' ? 'text' : 'password';
    });

    // 保存配置
    $('#btn-save-config').addEventListener('click', saveConfig);

    // 主题切换
    $('#btn-theme').addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme') || 'dark';
      const next = current === 'dark' ? 'light' : 'dark';
      applyTheme(next);
      const sel = $('#setting-theme');
      if (sel) sel.value = next;
    });

    $('#setting-theme').addEventListener('change', (e) => {
      applyTheme(e.target.value);
    });

    // 语言切换
    const langSel = $('#setting-lang');
    if (langSel) {
      langSel.addEventListener('change', (e) => {
        setLang(e.target.value);
      });
    }

    // Documents drawer
    $('#btn-documents').addEventListener('click', openDocumentsDrawer);
    $('#btn-close-documents').addEventListener('click', closeDocumentsDrawer);
    $('#documents-drawer .drawer-backdrop').addEventListener('click', closeDocumentsDrawer);
    $('#btn-new-doc').addEventListener('click', createNewDocument);
    const docEditor = $('#doc-editor');
    if (docEditor) {
      docEditor.addEventListener('input', () => {
        updateActiveDocContent(docEditor.value);
        renderDocPreview();
      });
    }
    $('#btn-ai-assist').addEventListener('click', aiAssistDocument);
    $('#btn-doc-download').addEventListener('click', downloadActiveDoc);

    // 窗口控制（Electron）
    if (window.nexusDesktop && window.nexusDesktop.send) {
      // 已预留
    }
  }

  // ═══════════════════════════════════════════════
  // 启动
  // ═══════════════════════════════════════════════


  // ═══════════════════════════════════════════════
  // Document Editor
  // ═══════════════════════════════════════════════

  function initDocs() {
    try {
      const raw = localStorage.getItem(STORAGE_DOCS);
      if (raw) docs = JSON.parse(raw);
    } catch (e) { docs = []; }
    if (!Array.isArray(docs)) docs = [];
    if (docs.length === 0) {
      docs = [{ id: 'doc_' + Date.now(), title: t('doc_editor.untitled'), content: '', updatedAt: Date.now() }];
      saveDocs();
    }
    activeDocId = docs[0].id;
  }

  function saveDocs() {
    try {
      localStorage.setItem(STORAGE_DOCS, JSON.stringify(docs));
    } catch (e) { console.error('saveDocs failed:', e); }
  }

  function openDocumentsDrawer() {
    $('#documents-drawer').classList.remove('hidden');
    isDocDrawerOpen = true;
    renderDocTabs();
    loadActiveDoc();
  }

  function closeDocumentsDrawer() {
    $('#documents-drawer').classList.add('hidden');
    isDocDrawerOpen = false;
  }

  function createNewDocument() {
    const id = 'doc_' + Date.now();
    const doc = { id, title: t('doc_editor.untitled'), content: '', updatedAt: Date.now() };
    docs.push(doc);
    activeDocId = id;
    saveDocs();
    renderDocTabs();
    loadActiveDoc();
  }

  function deleteDocument(id) {
    if (!confirm(t('doc_editor.confirm_delete'))) return;
    docs = docs.filter(d => d.id !== id);
    if (docs.length === 0) {
      createNewDocument();
      return;
    }
    if (activeDocId === id) activeDocId = docs[0].id;
    saveDocs();
    renderDocTabs();
    loadActiveDoc();
  }

  function switchDocument(id) {
    // Save current before switching
    const editor = $('#doc-editor');
    if (editor) updateActiveDocContent(editor.value);
    activeDocId = id;
    renderDocTabs();
    loadActiveDoc();
  }

  function updateActiveDocContent(text) {
    const doc = docs.find(d => d.id === activeDocId);
    if (!doc) return;
    doc.content = text;
    doc.updatedAt = Date.now();
    // Auto-rename from first heading
    const m = text.match(/^#\s+(.+)$/m);
    if (m && (doc.title === t('doc_editor.untitled') || doc.title.startsWith(t('doc_editor.untitled')))) {
      doc.title = m[1].trim().slice(0, 30);
    }
    saveDocs();
  }

  function renderDocTabs() {
    const container = $('#doc-tabs');
    if (!container) return;
    container.innerHTML = '';
    docs.forEach(d => {
      const el = document.createElement('div');
      el.className = 'doc-tab' + (d.id === activeDocId ? ' active' : '');
      el.innerHTML = `<span>${escapeHtml(d.title)}</span><span class="doc-tab-close" title="Delete">×</span>`;
      el.addEventListener('click', (e) => {
        if (e.target.classList.contains('doc-tab-close')) {
          e.stopPropagation();
          deleteDocument(d.id);
        } else {
          switchDocument(d.id);
        }
      });
      container.appendChild(el);
    });
  }

  function loadActiveDoc() {
    const doc = docs.find(d => d.id === activeDocId);
    const editor = $('#doc-editor');
    if (!editor || !doc) return;
    editor.value = doc.content;
    renderDocPreview();
  }

  function renderDocPreview() {
    const editor = $('#doc-editor');
    const preview = $('#doc-preview');
    if (!editor || !preview) return;
    preview.innerHTML = renderMarkdown(editor.value);
  }

  async function aiAssistDocument() {
    const editor = $('#doc-editor');
    if (!editor) return;
    const selected = editor.value.substring(editor.selectionStart, editor.selectionEnd);
    const fullText = editor.value;
    let promptText = '';
    if (selected) {
      promptText = 'Rewrite, improve, or continue the following text. Only return the improved text, no explanations.\n\n' + selected;
    } else if (fullText) {
      promptText = 'Continue the following text naturally. Only return the continuation, no explanations.\n\n' + fullText.slice(-500);
    } else {
      promptText = 'Write a short introduction. Only return the text, no explanations.';
    }

    const btn = $('#btn-ai-assist');
    const original = btn ? btn.textContent : 'AI';
    if (btn) btn.textContent = '...';

    try {
      const res = await fetch(API_BASE + '/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: promptText, session: 'doc_ai_' + Date.now() }),
      });
      const data = await res.json();
      if (data.ok) {
        let aiText = data.response || '';
        // Strip markdown code fences if present
        aiText = aiText.replace(/^```\w*\n?/, '').replace(/\n?```$/, '').trim();
        if (selected) {
          const start = editor.selectionStart;
          const end = editor.selectionEnd;
          editor.value = editor.value.substring(0, start) + aiText + editor.value.substring(end);
          editor.selectionStart = editor.selectionEnd = start + aiText.length;
        } else {
          editor.value += (editor.value && !editor.value.endsWith('\n\n') ? '\n\n' : '') + aiText;
        }
        updateActiveDocContent(editor.value);
        renderDocPreview();
      }
    } catch (e) {
      showAlertToast('error', 'AI Assist', e.message || 'Failed');
    } finally {
      if (btn) btn.textContent = original;
    }
  }

  function downloadActiveDoc() {
    const doc = docs.find(d => d.id === activeDocId);
    if (!doc) return;
    const filename = (doc.title || 'untitled').replace(/[^a-zA-Z0-9\u4e00-\u9fa5_-]/g, '_') + '.md';
    downloadFile(filename, doc.content, 'text/markdown');
  }

  document.addEventListener('DOMContentLoaded', init);
})();
