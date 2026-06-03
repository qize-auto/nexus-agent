# NexusAgent 截图素材说明

> 以下截图用于 README.md 展示，请按步骤捕获后替换占位文件。

---

## 需要捕获的截图

### 1. hero-dark.png — 主界面全景

**捕获步骤**：
1. 启动 Web UI：`python -m nexusagent.interface.adapter`
2. 浏览器访问 `http://localhost:8080`
3. 发送一条测试消息（如"帮我写一个 Python 快速排序"）
4. 等待回复完成
5. 按 `F12` → 打开 Device Toolbar → 选择 `Responsive` 尺寸 `1440x900`
6. 截图保存为 `hero-dark.png`

**要求**：
- 暗黑模式
- 展示完整的对话流程（用户消息 + AI 回复）
- 可见左侧边栏、顶部模型信息、消息气泡

---

### 2. web-ui-dark.png — Web UI 对话界面

**捕获步骤**：
1. 启动 Web UI
2. 发送一条多轮对话（至少 3 轮）
3. 截图保存为 `web-ui-dark.png`

**要求**：
- 展示消息气泡样式（用户蓝色、AI 灰色）
- 可见代码块渲染（如有代码）
- 展示滚动条位置（有历史消息）

---

### 3. web-ui-welcome.png — 欢迎页功能卡片

**捕获步骤**：
1. 启动 Web UI
2. 点击"新对话"按钮
3. 截图保存为 `web-ui-welcome.png`

**要求**：
- 展示欢迎页 Logo 和副标题
- 可见 4 个功能卡片（代码助手、文档分析、图像理解、联网搜索）

---

### 4. cli-mode.png — CLI 命令行模式

**捕获步骤**：
1. 打开终端
2. 运行 `python -m nexusagent.main`
3. 发送几条消息，展示不同模式：
   - 一条闲聊（如"你好"）
   - 一条任务（如"帮我写一个斐波那契函数"）
4. 按 `Ctrl+C` 退出
5. 运行 `nexus doctor`，展示诊断输出
6. 截图保存为 `cli-mode.png`

**要求**：
- 可见 NexusAgent 启动 Logo
- 可见严谨模式激活提示
- 可见 `nexus doctor` 诊断结果

---

## 截图规范

| 项目 | 要求 |
|------|------|
| 尺寸 | 宽度 1200-1600px，高度自适应 |
| 格式 | PNG（推荐）或 WebP |
| 背景 | 保持原样（暗黑模式优先） |
| 命名 | 严格使用上述文件名 |
| 压缩 | 建议用 tinypng.com 压缩，单张 < 500KB |

---

## 快速截图脚本（Windows）

```powershell
# 启动服务
Start-Process powershell -ArgumentList "python -m nexusagent.interface.adapter" -WindowStyle Hidden
Start-Sleep 5

# 用 Chrome 截图（需安装 headless chrome）
chrome --headless --screenshot=hero-dark.png --window-size=1440,900 http://localhost:8080
```

---

## 占位说明

当前 README.md 中引用的截图路径：

```markdown
<img src="docs/screenshots/hero-dark.png">
<img src="docs/screenshots/web-ui-dark.png">
<img src="docs/screenshots/web-ui-welcome.png">
<img src="docs/screenshots/cli-mode.png">
```

请捕获后按上述文件名保存到本目录，README 会自动加载。
