# NexusAgent Quickstart

> Get up and running in 5 minutes — Personal AI Agent System v4.0+

---

## Installation

### Requirements

- Python 3.10+
- (Optional) Docker + Docker Compose

### Install Dependencies

```bash
git clone <repository-url>
cd nexusagent
pip install -r requirements.txt
```

### Set the Master Key

NexusAgent uses AES-256-GCM to encrypt memory data. **Set a master key before the first run.**

```bash
# Generate a key
export NEXUS_MASTER_KEY=$(python -c 'import base64,os;print(base64.b64encode(os.urandom(32)).decode())')

# Save to .env (recommended)
echo "NEXUS_MASTER_KEY=$NEXUS_MASTER_KEY" > .env
```

> If not set, the agent auto-generates a temporary key and prints a warning. Temporary keys are lost when the process ends, and previously encrypted data will become unreadable.

---

## Configuration

### Minimal Config

Create `config.yaml` (optional — zero-config startup works):

```yaml
model:
  default_provider: deepseek
  default_model: deepseek-chat

channels:
  enabled_channels: ["cli"]
```

### Environment Variable Overrides

All config values can be overridden via environment variables:

```bash
export NEXUS_DEBUG=true
export DEEPSEEK_API_KEY=your-key-here
```

---

## Launch

### Interactive CLI (default)

```bash
python -m nexusagent.main
```

Type `exit` or press Ctrl+C to quit.

### Web Mode

```bash
python -m nexusagent.interface.adapter
```

Open browser at `http://localhost:8080`

### Docker Deploy

```bash
docker-compose up -d
```

---

## Core Features

### Strict Execution Mode

NexusAgent auto-detects whether your message is a **task** or **chat**. Tasks enter Strict Mode:

```
>>> Write a Python function to compute Fibonacci numbers
[Strict Mode activated]
[Executing...]
[Delivery report]
```

Manual mode switch:

```bash
# Force strict mode
nexus mode strict

# Force chat mode
nexus mode chat

# Auto-detect (default)
nexus mode auto

# View current mode
nexus mode status
```

### Tool Management

```bash
# List all tools
nexus tool ls

# View tool details
nexus tool info <name>

# Search tools
nexus tool search <keyword>
```

### User Profile

```bash
# View current profile
nexus profile show

# Explicit teaching
nexus profile learn "I prefer detailed code comments"

# Delete profile (GDPR)
nexus profile forget
```

### Dream Engine

```bash
# Manually trigger profile processing
nexus dream now
```

### Self-Evolution

```bash
# View evolution system status
nexus evolution status

# Manually trigger evolution cycle
nexus evolution run

# View pending proposals
nexus evolution review

# Switch mode
nexus evolution mode <off|notify|auto>
```

### Diagnostics

```bash
# Run full diagnostics
nexus doctor

# View component status
nexus status
```

### Memory Backup

```bash
# Create backup
nexus backup create

# List backups
nexus backup list

# Restore backup
nexus backup restore <timestamp>
```

---

## Common Config Examples

### Use Ollama Local Model

```yaml
model:
  default_provider: ollama
  default_model: llama3.2
  providers:
    ollama:
      base_url: http://localhost:11434
```

### Enable Multiple Channels

```yaml
channels:
  enabled_channels: ["cli", "telegram"]
  telegram:
    token: "your-telegram-bot-token"
```

### Adjust Strict Mode

```yaml
strict:
  mode: auto
  max_clarify_rounds: 3
  max_retry_attempts: 3
  enable_deliberation: true
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `NEXUS_MASTER_KEY not set` | Run `export NEXUS_MASTER_KEY=...` or check `.env` file |
| `ModuleRegistry bootstrap failed` | Safe to ignore — agent falls back to legacy initialization |
| `LLM connection timeout` | Check network, API key validity, model availability |
| `Tests failing` | Run `nexus eval` for details |
| `Port already in use` | Change port in `config.yaml` |

---

## Next Steps

- Read [VERIFICATION_CHECKLIST.md](VERIFICATION_CHECKLIST.md) for feature verification status
- Read [AGENTS.md](../AGENTS.md) for architecture design
- Run `nexus doctor` to check system health
