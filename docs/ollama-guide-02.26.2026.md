# Ollama on Pi 5 — Reference Guide
*bryanfoslerpi5 — updated 02.26.2026*

---

## What's Running

| Service | Port | Purpose |
|---------|------|---------|
| `ollama` | 11434 | LLM inference engine + REST API |
| `open-webui` | 3000 | Browser-based chat UI |

---

## Access

```bash
# Chat UI — open in any browser on your network
http://bryanfoslerpi5.local:3000

# Raw API
http://bryanfoslerpi5.local:11434
```

---

## Managing Models

```bash
# List installed models
ollama list

# Pull a new model
ollama pull llama3.2:3b       # ~2GB  — fast, good default
ollama pull llama3.2:1b       # ~1.3GB — very fast, lighter
ollama pull mistral:7b        # ~4.1GB — more capable, slower
ollama pull moondream2        # ~1.8GB — vision model (describes images)

# Remove a model
ollama rm <model-name>

# Show model info
ollama show llama3.2:3b
```

### Pi 5 (8GB) Model Performance Guide

| Model | Size | Speed | Best for |
|-------|------|-------|---------|
| `llama3.2:1b` | 1.3GB | ~15-20 tok/s | Quick answers, low latency |
| `llama3.2:3b` | 2GB | ~8-12 tok/s | Good balance — recommended default |
| `mistral:7b` | 4.1GB | ~3-5 tok/s | More nuanced tasks, patient use |
| `moondream2` | 1.8GB | slow | Image description (pet cam) |

---

## Quick Chat (Terminal)

```bash
# Interactive chat with a model
ollama run llama3.2:3b

# Single prompt (non-interactive)
ollama run llama3.2:3b "What is the capital of France?"

# Exit interactive chat
/bye
```

---

## API Usage

The Ollama API is available at `http://bryanfoslerpi5.local:11434` from any device on the network.

```bash
# List available models
curl http://bryanfoslerpi5.local:11434/api/tags

# Generate a completion (streaming)
curl http://bryanfoslerpi5.local:11434/api/generate \
  -d '{"model": "llama3.2:3b", "prompt": "Why is the sky blue?"}'

# Generate (no streaming — wait for full response)
curl http://bryanfoslerpi5.local:11434/api/generate \
  -d '{"model": "llama3.2:3b", "prompt": "Why is the sky blue?", "stream": false}'

# Chat with history
curl http://bryanfoslerpi5.local:11434/api/chat \
  -d '{
    "model": "llama3.2:3b",
    "messages": [
      {"role": "user", "content": "What is the speed of light?"}
    ]
  }'
```

---

## Service Management

```bash
# Check status
sudo systemctl status ollama
sudo systemctl status open-webui

# Restart
sudo systemctl restart ollama
sudo systemctl restart open-webui

# View logs
journalctl -u ollama -f
journalctl -u open-webui -f

# Stop / Start
sudo systemctl stop ollama
sudo systemctl start ollama
```

---

## Configuration

**Ollama network binding** (set in `/etc/systemd/system/ollama.service.d/override.conf`):
```ini
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
```
Remove this override if you want to restrict Ollama to localhost only.

**Models are stored at:** `~/.ollama/models/`

**Open-WebUI data at:** `~/.open-webui/`

---

## Troubleshooting

| Problem | Check |
|---------|-------|
| Open-WebUI shows "Ollama not connected" | `sudo systemctl status ollama` — must be running |
| Model download stalled | `journalctl -u ollama -f` — may be slow on first pull |
| Response very slow | Try a smaller model (`llama3.2:1b`) |
| Can't reach from Mac | Confirm `OLLAMA_HOST=0.0.0.0` override is in place |
| Open-WebUI won't load | `journalctl -u open-webui -n 50` — check for errors |

---

## Coming Next: Vision / Pet Cam

To add image recognition:
1. Pull the vision model: `ollama pull moondream2`
2. Add a Pi Camera Module 3 or USB webcam
3. Capture frames and POST them to the Ollama vision API

```bash
# Describe an image (once moondream2 is installed)
curl http://localhost:11434/api/generate \
  -d '{
    "model": "moondream2",
    "prompt": "Describe what you see in this image.",
    "images": ["<base64-encoded-image>"]
  }'
```
