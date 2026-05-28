# Velum · LLM PII Firewall

A transparent proxy that automatically detects and redacts personally identifiable information before it reaches the LLM, then restores it in responses. The LLM never sees the original data.

```
User → Any Client → [Velum] → LLM API
                      ↑
            Redact → Forward → Restore → User
```

## Prerequisites

| Requirement | Note |
|-------------|------|
| Docker | 24+, with docker compose |
| Upstream LLM API | Any OpenAI-compatible API (DMXAPI, OpenAI, etc.) |
| Memory | ≥ 1GB (HanLP model ~400MB) |

## Deployment

### Option 1: Standalone Docker

```bash
git clone https://github.com/Trojan-Seahorse/velum.git
cd velum
docker build -t velum .
docker run -d -p 8000:8000 \
  -e UPSTREAM_URL=https://your-llm-api.com/v1 \
  -e ARGUS_REDACT_PSEUDONYM_SALT=$(openssl rand -hex 16) \
  --name velum velum
```

Verify:

```bash
curl http://localhost:8000/health
# → {"status":"ok","upstream":"https://your-llm-api.com/v1","pii":"ok"}
```

### Option 2: Docker Compose (with Hermes Gateway)

```yaml
# docker-compose.yml (place in velum repo root)
services:
  velum:
    build: .
    container_name: velum
    ports:
      - "127.0.0.1:17829:8000"
    volumes:
      - ./location_names.txt:/app/location_names.txt:ro
    environment:
      - PYTHONUNBUFFERED=1
      - UPSTREAM_URL=https://your-llm-api.com/v1
      - PII_ENABLED=true
      - ARGUS_REDACT_PSEUDONYM_SALT=your-random-salt-here
    restart: unless-stopped
    mem_limit: 1g

  hermes:
    image: nousresearch/hermes-agent:latest
    container_name: hermes
    command: ["gateway", "run"]
    volumes:
      - ./hermes:/opt/data
    environment:
      - API_SERVER_ENABLED=true
      - API_SERVER_HOST=0.0.0.0
      - API_SERVER_KEY=your-api-key
    depends_on:
      - velum
    restart: unless-stopped
```

> **Important**: Hermes stores its LLM backend URL in `./hermes/config.yaml` and `./hermes/auth.json` — set both to `http://velum:8000/v1`. This is NOT configured via environment variable.

```bash
# Create Hermes data directory and config
mkdir -p hermes
# Edit ./hermes/config.yaml, set base_url: http://velum:8000/v1
# Edit ./hermes/auth.json, set base_url: http://velum:8000/v1

docker compose up -d
docker logs -f velum
```

### Client Configuration

Point your LLM client to Velum's address. Use your upstream LLM API key — Velum proxies it, never stores it.

| Client | Configuration |
|--------|--------------|
| CherryStudio | Settings → Model Services → API URL: `http://your-host:17829/v1` |
| Hermes | `config.yaml` + `auth.json`: `base_url: http://velum:8000/v1` |
| OpenAI SDK | `base_url="http://your-host:8000/v1"` |

## Daily Use

Prepend `!pii` to your message to switch redaction mode for that message. Messages without the prefix use the default strategy. Both full-width `！` and half-width `!` are accepted.

| Command | Effect |
|---------|--------|
| `!pii` | Show firewall status and strategy |
| `!pii debug <text>` | Analyze PII detection without calling the LLM |
| `!pii pseudonym` | Use realistic fake names (other types still redacted) |
| `!pii org,loc` | Keep organization and location names unredacted |

Example:

```
User: !pii debug Zhang Wei works at SIPAC, phone 13900001111

Original: Zhang Wei works at SIPAC, phone 13900001111
Redacted: P-47141 works at P-72185, phone T-39281
Entities: 3

Detected:
  [1] person  Zhang Wei → P-47141
  [2] person  Suzhou Industrial Park → P-72185
  [3] phone   13900001111 → T-39281

User: Help me summarize   ← Next message, no prefix — back to default mode
```

### Redaction Strategies

| Entity Type | Strategy | Example |
|-------------|----------|---------|
| person | remove | Li Ming → P-00128 |
| organization | remove | Acme Corp → O-09502 |
| school | remove | MIT → S-14439 |
| location | remove | Beijing → L-23017 |
| phone | remove | 13900001111 → T-39281 |
| email | remove | a@b.com → E-55612 |
| id_number | remove | 110101... → I-78403 |
| address | remove | 200 Tianfu Ave → A-66194 |
| bank_card | mask | 622202... → ****0123 |
| self_reference | keep | (untouched) |
| date | remove | 2024-03-15 → D-33501 |

## Environment Variables

| Variable | Required | Description |
|----------|:--------:|-------------|
| `UPSTREAM_URL` | ✅ | Upstream LLM API URL, e.g. `https://www.dmxapi.cn/v1` |
| `ARGUS_REDACT_PSEUDONYM_SALT` | ✅ | Salt for pseudonym generation — use a random string |
| `PII_ENABLED` | — | Set to `false` to disable redaction (default `true`) |

## Troubleshooting

### `/health` returns `pii: error`

HanLP model download failed. Check container network and manually warm up:

```bash
docker exec velum python -c "from argus_redact import redact; redact('test', lang='zh')"
```

### `!pii debug` shows missed detections

Short text (< 8 characters) or locations with non-standard administrative suffixes (e.g. "Suzhou Industrial Park") may be missed by NER. This is a known HanLP limitation.

- **Workaround**: Use `!pii pseudonym` for that message
- **Permanent fix**: Add the missed location to `location_names.txt` and restart the container

### Upstream LLM connection timeout

```bash
# Check environment variable
docker exec velum env | grep UPSTREAM_URL

# Verify container can reach upstream
docker exec velum python -c "import httpx; r = httpx.get('$UPSTREAM_URL/models'); print(r.status_code)"
```

### Container OOM

HanLP model is ~400MB and pre-downloaded at build time. Allocate ≥ 1GB at runtime:

```bash
docker run --memory=1g ...          # standalone
mem_limit: 1g                        # docker compose
```

## License

MIT

---

[中文文档](README.md)
