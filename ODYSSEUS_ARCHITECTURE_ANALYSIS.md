# NexusAgent vs Odysseus 架构深度调研报告

> **调研目标**: 分析 NexusAgent 是否能复刻 Odysseus 的架构（Ollama + FastAPI + PWA），如不能，给出调整方案。

---

## 一、Odysseus 架构拆解

### 1.1 技术栈
| 层级 | 技术 | 说明 |
|------|------|------|
| **后端** | Python 3.11 + FastAPI + uvicorn | 现代化 ASGI 框架，自动 OpenAPI 文档 |
| **前端** | 纯 HTML/CSS/JS (PWA) | 响应式，支持移动端，可安装为 PWA |
| **LLM 后端** | Ollama（本地）/ OpenRouter / OpenAI | 本地优先，云端可选 |
| **向量存储** | ChromaDB + fastembed (ONNX) | 本地嵌入，无需联网 |
| **数据库** | SQLite（默认）/ PostgreSQL | 会话、消息、文档存储 |
| **搜索** | SearXNG（自托管）| 本地聚合搜索，保护隐私 |
| **通知** | ntfy | 本地推送通知 |
| **容器** | Docker Compose | 一键启动所有服务 |

### 1.2 核心功能矩阵
| 功能 | 依赖 LLM | 本地可行性 |
|------|---------|-----------|
| 聊天 (Chat) | ✅ 必须 | ✅ Ollama 本地运行 |
| Agent 工具调用 | ✅ 必须 | ✅ 本地 LLM + 本地工具 |
| Cookbook（模型管理）| ❌ 不依赖 | ✅ 纯本地硬件扫描 + 下载 |
| Deep Research | ✅ 必须 | ✅ 本地 LLM + SearXNG |
| 文档编辑 | ⚠️ AI 辅助需 LLM | ✅ 编辑器本身离线 |
| Memory/Skills | ⚠️ 嵌入需 ONNX | ✅ fastembed 本地运行 |
| 邮件/日历 | ⚠️ AI triage 需 LLM | ✅ IMAP/SMTP/CalDAV 本身离线 |
| 图片/音频/视频 | ✅ 多模态需 LLM | ⚠️ 需本地多模态模型 |

### 1.3 Docker Compose 架构
```yaml
services:
  odysseus:       # FastAPI 主应用
  chromadb:       # 向量数据库
  searxng:        # 自托管搜索引擎
  ntfy:           # 推送通知
```

---

## 二、NexusAgent 当前架构盘点

### 2.1 技术栈
| 层级 | 技术 | 说明 |
|------|------|------|
| **后端** | Python 3.10+ asyncio + aiohttp | WebAdapter 基于 aiohttp，非 FastAPI |
| **前端 (Web)** | 纯 HTML/CSS/JS (web_ui/) | **极其简陋**，仅工具状态页面 |
| **前端 (Desktop)** | PyQt6 + QWebChannel | **这才是真正的 UI**，完整聊天界面 |
| **LLM 后端** | litellm 统一调用 | 支持 OpenAI 兼容接口，间接支持 Ollama |
| **向量存储** | sqlite-vec | SQLite 扩展，轻量但功能有限 |
| **数据库** | SQLite | MemoryStore, DiagnosticStore |
| **搜索** | ❌ 无 | 没有任何搜索能力 |
| **容器** | Docker Compose | 仅 Redis，无 ChromaDB/SearXNG |

### 2.2 核心功能矩阵
| 功能 | 实现状态 | 依赖 LLM | 本地可行性 |
|------|---------|---------|-----------|
| 聊天 (Chat) | ✅ CLI + Web + Desktop | ✅ 必须 | ⚠️ 间接支持 Ollama |
| Agent 工具调用 | ✅ ReActEngine | ✅ 必须 | ⚠️ 间接支持 |
| Cookbook（模型管理）| ❌ 无 | N/A | N/A |
| Deep Research | ❌ 无 | N/A | N/A |
| 文档编辑 | ❌ 无 | N/A | N/A |
| Memory/Skills | ✅ HybridMemory | ⚠️ sqlite-vec | ✅ 纯本地 |
| 邮件/日历 | ❌ 无 | N/A | N/A |
| 多模态 | ❌ 无 | N/A | N/A |
| PWA | ❌ 无 | N/A | N/A |
| 移动端适配 | ❌ 无 | N/A | N/A |

---

## 三、差距分析：NexusAgent 能否复刻 Odysseus 架构？

### 3.1 直接回答

> **NexusAgent 当前无法直接复刻 Odysseus 的完整架构。核心差距在前端（PWA）和周边生态（搜索、Cookbook、多模态），而非后端 Agent 核心能力。**

### 3.2 逐项差距评估

| 维度 | NexusAgent | Odysseus | 差距等级 | 说明 |
|------|-----------|----------|---------|------|
| **后端框架** | aiohttp | FastAPI | 🟡 中 | aiohttp 功能足够，FastAPI 生态更好但非必需 |
| **前端** | PyQt6 桌面 + 空壳 Web | 完整 PWA | 🔴 **大** | NexusAgent 没有真正的 Web UI |
| **PWA** | 无 manifest/service worker | 完整 PWA | 🔴 **大** | 需要从零构建 |
| **本地 LLM** | 间接（litellm OpenAI 兼容）| 原生 Ollama | 🟡 中 | 功能可行但缺少 Cookbook 体验 |
| **Ollama Provider** | 无显式配置 | 原生深度集成 | 🟢 小 | 容易添加 |
| **向量存储** | sqlite-vec | ChromaDB + fastembed | 🟡 中 | sqlite-vec 轻量但功能弱于 ChromaDB |
| **搜索** | 无 | SearXNG | 🟡 中 | 可集成 SearXNG 或 DuckDuckGo |
| **Cookbook** | 无 | 硬件扫描 + 模型管理 | 🔴 **大** | 需要大量新开发 |
| **多模态** | 无 | 图片/音频/视频 | 🔴 **大** | 需本地多模态模型支持 |
| **邮件/日历** | 无 | IMAP/SMTP + CalDAV | 🔴 **大** | 非核心但增加生态完整性 |
| **移动端** | 不支持 | PWA 响应式 | 🔴 **大** | PyQt6 桌面无法迁移到手机 |
| **Docker** | 基础（仅 Redis）| 完整（+ChromaDB+SearXNG+ntfy）| 🟡 中 | compose 文件需要扩展 |

### 3.3 关键瓶颈分析

#### 🔴 瓶颈 1：前端架构完全不同
- **Odysseus**: 前端是浏览器中运行的 PWA（HTML/CSS/JS），后端通过 HTTP/WebSocket 通信。
- **NexusAgent**: "真正"的 UI 在 `desktop/`（PyQt6 + QWebChannel），`web_ui/` 目录几乎为空。
- **问题**: PyQt6 桌面应用无法运行在手机上，也无法通过浏览器访问。Odysseus 的 PWA 可以同时覆盖桌面端和移动端。

#### 🔴 瓶颈 2：缺少本地模型管理（Cookbook）
- **Odysseus**: 扫描硬件 → 推荐模型 → 一键下载 → 自动 serve。用户体验是"开箱即用"。
- **NexusAgent**: 用户必须手动安装 Ollama、手动下载模型、手动配置 API endpoint。
- **问题**: 对于"本地优先"定位的产品，缺少 Cookbook 意味着用户门槛极高。

#### 🟡 瓶颈 3：向量存储能力差距
- **Odysseus**: ChromaDB 支持复杂向量查询、元数据过滤、多集合管理。
- **NexusAgent**: sqlite-vec 是 SQLite 扩展，功能有限（单表、简单相似度查询）。
- **问题**: 随着记忆数据增长，sqlite-vec 的性能和功能会成为瓶颈。

#### 🟡 瓶颈 4：后端框架差异
- **Odysseus**: FastAPI 提供自动 API 文档（Swagger）、类型校验、依赖注入、中间件生态丰富。
- **NexusAgent**: aiohttp 需要手工注册路由、手工写请求校验、无自动生成文档。
- **问题**: 不是功能缺失，而是开发效率和生态差距。FastAPI 更容易集成第三方库（如 LangChain、LlamaIndex）。

---

## 四、调整方案：NexusAgent → Odysseus 化改造

### 4.1 方案总览

```
Phase 1（核心必做）: PWA 前端 + Ollama 原生支持
Phase 2（重要）:     ChromaDB 可选集成 + SearXNG 搜索
Phase 3（增强）:     Cookbook + 多模态 + 邮件/日历
Phase 4（可选）:     FastAPI 迁移
```

---

### 4.2 Phase 1: PWA 前端 + Ollama 原生支持（最高优先级）

#### 4.2.1 前端改造：PyQt6 → PWA

**现状**: `desktop/` 有完整的 PyQt6 UI（index.html + app.js + styles.css + bridge.py），`web_ui/` 几乎为空。

**方案**: 将 `desktop/` 的 UI 资产改造为 PWA，同时保留 PyQt6 桌面端作为可选方案。

**具体步骤**:

1. **新建 `web/` 目录**（替代/扩展 `web_ui/`）
   ```
   web/
   ├── index.html          # 主入口（从 desktop/index.html 改造）
   ├── app.js              # 主逻辑（从 desktop/app.js 改造）
   ├── styles.css          # 样式（从 desktop/styles.css 改造）
   ├── manifest.json       # PWA 配置（新增）
   ├── sw.js               # Service Worker（新增）
   └── icons/              # PWA 图标
   ```

2. **核心改造点**:
   - 将 `QWebChannel` 通信替换为 `fetch`/`WebSocket` 调用后端 API
   - 添加 `manifest.json`:
     ```json
     {
       "name": "NexusAgent",
       "short_name": "Nexus",
       "start_url": "/",
       "display": "standalone",
       "background_color": "#0d1117",
       "theme_color": "#58a6ff",
       "icons": [{"src": "/icon.png", "sizes": "192x192"}]
     }
     ```
   - 添加 Service Worker 实现离线缓存

3. **WebAdapter 增强**:
   - 当前 WebAdapter 已经提供 `/api/chat`, `/ws`, `/api/health` 等端点
   - 需要新增:
     - `POST /api/chat/stream` — SSE 流式输出（替代 WebSocket 或作为补充）
     - `GET /api/models` — 列出可用模型
     - `POST /api/models/pull` — 触发模型下载（Cookbook 前置）
     - `GET /api/sessions` — 会话列表
     - `GET /api/memory/search?q=xxx` — 记忆检索

#### 4.2.2 Ollama 原生支持

**现状**: NexusAgent 通过 litellm 的 OpenAI 兼容接口间接支持 Ollama，但没有显式配置。

**方案**: 在 ProviderRegistry 中新增 Ollama provider，并添加本地模型发现功能。

**代码修改**:
```python
# models/unified_backend.py
"ollama": ProviderConfig(
    name="ollama",
    display_name="Ollama (Local)",
    base_url="http://localhost:11434/v1",
    api_key_env="",  # Ollama 默认不需要 key
    default_model="llama3.2",
    model_prefix="ollama/",
    region="local",
),
```

**新增 API 端点**:
```python
# interface/adapter.py WebAdapter
async def _handle_models(self, request):
    """GET /api/models — 列出本地和远程可用模型"""
    # 1. 查询 Ollama 本地模型: GET http://localhost:11434/api/tags
    # 2. 合并 ProviderRegistry 中配置的模型
    # 3. 返回统一格式
```

---

### 4.3 Phase 2: ChromaDB 可选集成 + SearXNG 搜索

#### 4.3.1 ChromaDB 作为可选向量后端

**现状**: HybridMemory 固定使用 sqlite-vec。

**方案**: 抽象 VectorStore 接口，支持 sqlite-vec（默认）和 ChromaDB（可选）。

**新增文件**:
```python
# memory/vector_store.py
from abc import ABC, abstractmethod

class VectorStore(ABC):
    @abstractmethod
    async def add(self, id: str, text: str, embedding: list[float], metadata: dict): ...
    @abstractmethod
    async def search(self, query_embedding: list[float], top_k: int = 5, filters: dict = None): ...

class SQLiteVecStore(VectorStore): ...  # 现有逻辑迁移
class ChromaDBStore(VectorStore): ...   # 新增
```

**docker-compose.yml 扩展**:
```yaml
services:
  chromadb:
    image: chromadb/chroma:latest
    volumes:
      - chroma_data:/chroma/chroma
  searxng:
    image: searxng/searxng:latest
    volumes:
      - ./searxng/settings.yml:/etc/searxng/settings.yml:ro
```

#### 4.3.2 搜索工具集成

**新增工具**:
```python
# tools/search.py
class SearXNGSearchTool:
    """SearXNG 自托管搜索"""
    async def search(self, query: str) -> list[dict]:
        # 调用本地 SearXNG 实例
        # 返回标题/摘要/URL
```

---

### 4.4 Phase 3: Cookbook + 多模态 + 邮件/日历

#### 4.4.1 Cookbook（模型管理）

**功能设计**:
1. **硬件扫描**: 检测 GPU（NVIDIA/AMD/Apple Silicon）和可用 VRAM
2. **模型推荐**: 根据 VRAM 推荐合适的 GGUF/AWQ/FP8 模型
3. **一键下载**: 通过 Ollama 或 huggingface-cli 下载模型
4. **本地 Serve**: 自动启动 Ollama 或 llama.cpp 提供 API

**新增模块**:
```
nexusagent/cookbook/
├── __init__.py
├── hardware.py      # 硬件扫描
├── recommender.py   # 模型推荐引擎
├── downloader.py    # 模型下载
├── server.py        # 本地模型 serve 管理
```

**API 端点**:
```
GET  /api/cookbook/hardware      # 硬件信息
GET  /api/cookbook/recommend     # 推荐模型列表
POST /api/cookbook/pull          # 下载模型
POST /api/cookbook/serve         # 启动本地 serve
```

#### 4.4.2 多模态支持

**方案**: 利用 Ollama 的多模态模型（如 llava、bakllava）实现图片理解。

**修改**:
- `interface/adapter.py`: 支持图片上传端点
- `execution/react_engine.py`: 支持多模态 message format

#### 4.4.3 邮件/日历（可选）

**方案**: 通过 IMAP/SMTP 和 CalDAV 协议集成，作为可选模块。

---

### 4.5 Phase 4: FastAPI 迁移（可选）

**评估**: aiohttp 当前功能完整，FastAPI 迁移工作量较大但收益明显。

**收益**:
- 自动生成 OpenAPI/Swagger 文档
- 类型驱动的请求校验（Pydantic v2 原生支持）
- 更丰富的中间件生态（认证、CORS、限流等）
- 更容易集成 LlamaIndex、LangChain 等框架

**迁移策略**:
```python
# 新文件: interface/fastapi_adapter.py
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles

class FastAPIAdapter(ChannelAdapter):
    async def start(self):
        self._app = FastAPI(title="NexusAgent")
        self._app.mount("/static", StaticFiles(directory="web/"), name="static")
        
        @self._app.post("/api/chat")
        async def chat(req: ChatRequest): ...
        
        @self._app.websocket("/ws")
        async def websocket(websocket: WebSocket): ...
```

**风险**: FastAPI 和 aiohttp 的事件循环模型不同，需要仔细测试异步兼容性。

---

## 五、改造工作量估算

| Phase | 内容 | 预估工作量 | 优先级 |
|-------|------|-----------|--------|
| Phase 1.1 | PWA 前端（从 desktop/ 迁移） | 2-3 周 | 🔴 P0 |
| Phase 1.2 | Ollama provider + 模型发现 API | 3-5 天 | 🔴 P0 |
| Phase 2.1 | VectorStore 抽象 + ChromaDB 后端 | 1 周 | 🟡 P1 |
| Phase 2.2 | SearXNG 搜索工具 | 3-5 天 | 🟡 P1 |
| Phase 3.1 | Cookbook 硬件扫描 + 推荐 | 1-2 周 | 🟡 P1 |
| Phase 3.2 | Cookbook 下载 + serve | 1 周 | 🟡 P1 |
| Phase 3.3 | 多模态支持 | 1 周 | 🟢 P2 |
| Phase 3.4 | 邮件/日历 | 1-2 周 | 🟢 P2 |
| Phase 4 | FastAPI 迁移 | 2-3 周 | 🟢 P2 |

**总计**: 约 **8-12 周** 全职开发工作量，可达到 Odysseus 级别的本地优先 AI 工作区。

---

## 六、建议的最小可行改造（MVP）

如果资源有限，建议只做以下 **3 项**即可达到"可用"的本地优先状态：

1. **PWA 前端**（2-3 周）
   - 将 desktop/app.js + index.html 改造为纯浏览器 PWA
   - 通过 WebSocket/fetch 与后端通信
   - 这是最大的用户体验提升

2. **Ollama Provider**（3 天）
   - 在 ProviderRegistry 中显式注册 Ollama
   - 添加 `/api/models` 本地模型发现

3. **SearXNG 搜索工具**（3 天）
   - 添加一个搜索工具，让 Agent 具备联网能力
   - docker-compose 中添加 SearXNG 服务

**MVP 完成后**，NexusAgent 将具备：
- ✅ 浏览器中运行的完整聊天界面（桌面+手机）
- ✅ 本地 Ollama 模型支持（零 API Key）
- ✅ Agent 可搜索互联网
- ✅ 691 个测试继续通过

---

## 七、结论

| 问题 | 答案 |
|------|------|
| NexusAgent 能本地运行吗？ | ✅ 能，后端和 Agent 核心完全本地 |
| 能复刻 Odysseus 架构吗？ | ⚠️ 后端能力接近，前端和生态差距大 |
| 最大瓶颈是什么？ | 🔴 **前端** — PyQt6 桌面 UI 无法成为 PWA |
| 最小改造投入？ | 2-3 周（PWA 前端 + Ollama + 搜索）|
| 完整复刻投入？ | 8-12 周 |

> **建议**: NexusAgent 的 Agent 核心（ReAct + Swarm + MiroFish + 防偷懒机制）已经很强，**不需要重写**。真正的投资应该放在 **PWA 前端** 和 **本地 LLM 体验优化** 上。保留 PyQt6 桌面端作为"高级用户"选项，同时新建一个 PWA 前端覆盖 Web + 移动端。
