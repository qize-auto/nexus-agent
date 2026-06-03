# NexusAgent 快速开始指南

> 5 分钟上手 NexusAgent — 个人智能体系统 v4.0+

---

## 一、安装

### 1.1 环境要求

- Python 3.10+
- (可选) Docker + Docker Compose

### 1.2 安装依赖

```bash
git clone <repository-url>
cd nexusagent
pip install -r requirements.txt
```

### 1.3 设置主密钥

NexusAgent 使用 AES-256-GCM 加密记忆数据。**首次运行前必须设置主密钥**。

```bash
# 生成密钥
export NEXUS_MASTER_KEY=$(python -c 'import base64,os;print(base64.b64encode(os.urandom(32)).decode())')

# 保存到 .env 文件（推荐）
echo "NEXUS_MASTER_KEY=$NEXUS_MASTER_KEY" > .env
```

> 如果不设置，Agent 会自动生成临时密钥并打印警告。临时密钥在进程结束后丢失，已加密的数据将无法解密。

---

## 二、配置

### 2.1 最小配置

创建 `config.yaml`（可选，零配置也能启动）：

```yaml
model:
  default_provider: deepseek
  default_model: deepseek-chat

channels:
  enabled_channels: ["cli"]
```

### 2.2 环境变量覆盖

所有配置都可通过环境变量覆盖：

```bash
export NEXUS_DEBUG=true
export DEEPSEEK_API_KEY=your-key-here
```

---

## 三、启动

### 3.1 交互式 CLI（默认）

```bash
python -m nexusagent.main
```

输入 `exit` 或按 Ctrl+C 退出。

### 3.2 Web 模式

```bash
python -m nexusagent.interface.adapter
```

浏览器访问 `http://localhost:8080`

### 3.3 Docker 部署

```bash
docker-compose up -d
```

---

## 四、核心功能使用

### 4.1 严谨执行模式

NexusAgent 会自动检测你的请求是"任务"还是"闲聊"。任务请求会走严谨模式：

```
>>> 帮我写一个 Python 函数计算斐波那契数列
[严谨模式激活]
[执行中...]
[交付报告]
```

手动切换模式：

```bash
# 强制严谨模式
nexus mode strict

# 强制对话模式
nexus mode chat

# 自动检测（默认）
nexus mode auto

# 查看当前模式
nexus mode status
```

### 4.2 工具管理

```bash
# 列出所有工具
nexus tool ls

# 查看工具详情
nexus tool info <name>

# 搜索工具
nexus tool search <keyword>
```

### 4.3 用户画像

```bash
# 查看当前画像
nexus profile show

# 显式教学
nexus profile learn "我喜欢详细的代码注释"

# 删除画像 (GDPR)
nexus profile forget
```

### 4.4 梦境引擎

```bash
# 手动触发画像加工
nexus dream now
```

### 4.5 自我进化

```bash
# 查看进化系统状态
nexus evolution status

# 手动触发进化周期
nexus evolution run

# 查看待审批建议
nexus evolution review

# 切换模式
nexus evolution mode <off|notify|auto>
```

### 4.6 诊断检查

```bash
# 运行全部诊断
nexus doctor

# 查看组件状态
nexus status
```

### 4.7 记忆备份

```bash
# 创建备份
nexus backup create

# 列出备份
nexus backup list

# 恢复备份
nexus backup restore <timestamp>
```

---

## 五、常用配置示例

### 5.1 使用 Ollama 本地模型

```yaml
model:
  default_provider: ollama
  default_model: llama3.2
  providers:
    ollama:
      base_url: http://localhost:11434
```

### 5.2 启用多通道

```yaml
channels:
  enabled_channels: ["cli", "telegram"]
  telegram:
    token: "your-telegram-bot-token"
```

### 5.3 调整严谨模式

```yaml
strict:
  mode: auto
  max_clarify_rounds: 3
  max_retry_attempts: 3
  enable_deliberation: true
```

---

## 六、故障排除

| 问题 | 解决方案 |
|------|---------|
| `NEXUS_MASTER_KEY 未设置` | 运行 `export NEXUS_MASTER_KEY=...` 或检查 `.env` 文件 |
| `ModuleRegistry 引导失败` | 可忽略，Agent 会回退到现有初始化 |
| `LLM 连接超时` | 检查网络、API Key 是否正确、模型是否可用 |
| `测试失败` | 运行 `nexus eval` 查看详情 |
| `端口被占用` | 修改 `config.yaml` 中的端口配置 |

---

## 七、下一步

- 阅读 [VERIFICATION_CHECKLIST.md](VERIFICATION_CHECKLIST.md) 了解功能验证状态
- 阅读项目 `AGENTS.md` 了解架构设计
- 运行 `nexus doctor` 检查系统健康
