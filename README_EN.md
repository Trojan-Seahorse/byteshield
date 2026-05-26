# Velum · LLM PII Firewall

**A transparent proxy that automatically detects and redacts personally identifiable information before it reaches the LLM. Restores PII in responses before returning to the user.**

```
User → Hermes/Any Client → [Velum PII Firewall] → LLM API
                              ↑
                 Redact → Forward → Restore → User
```

## Why

LLM APIs are black boxes — your conversation data is logged, stored, and potentially used for model training. Sending messages containing real names, phone numbers, ID numbers, or addresses is equivalent to handing that data to a third party.

Velum intercepts PII before it leaves your network, replacing it with anonymous identifiers (e.g., `P-00128`, `L-23017`). The LLM never sees the original data. Responses are automatically restored — transparent to the user.

## Key Features

| Feature | Description |
|---------|-------------|
| **Transparent Proxy** | OpenAI-compatible API endpoint. Just change the URL. |
| **Multi-Mode Switch** | In-message `!pii` prefix toggles redaction strategies on the fly. |
| **Per-Type Identifier** | Each entity type uses a distinct prefix (P-person O-org L-loc T-phone...) — LLM can distinguish entity types. |
| **SSE Streaming Restore** | Full DeepSeek `reasoning_content` restoration. |
| **Compound Location Enhancement** | 430+ economic zone names (parks, new districts, etc.) to patch HanLP NER blind spots. |
| **Fail-Open** | Pass-through on error — never blocks service. |
| **Low Footprint** | Only argus-redact + FastAPI. Single container, < 500MB RAM. |

## Prerequisites

| Requirement | Note |
|-------------|------|
| Docker | 24+, with docker compose |
| LLM API | Any OpenAI-compatible API (DMXAPI, OpenAI, etc.) |
| Python | 3.12 (dev/testing only; deployment uses Docker) |
| Memory | ≥ 1GB (HanLP model ~400MB) |

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/Trojan-Seahorse/velum.git
cd velum

# 2. Build the image
docker build -t velum .

# 3. Start the container
docker run -d -p 8000:8000 \
  -e UPSTREAM_URL=https://your-llm-api.com/v1 \
  -e ARGUS_REDACT_PSEUDONYM_SALT=$(openssl rand -hex 16) \
  --name velum velum

# 4. Verify connectivity
curl http://localhost:8000/health
# → {"status": "ok", "pii_enabled": true}

# 5. Test PII redaction
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-api-key" \
  -d '{
    "model": "deepseek-chat",
    "messages": [
      {"role": "user", "content": "!pii debug Zhang Wei phone 13900001111"}
    ],
    "stream": true
  }'
```

> **Tip**: In step 3, `UPSTREAM_URL` points to your LLM API. `ARGUS_REDACT_PSEUDONYM_SALT` seeds deterministic pseudonym generation — use a random string.

### Docker Compose (with Hermes Gateway)

```yaml
# docker-compose.yml
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
      - ARGUS_REDACT_PSEUDONYM_SALT=your-random-salt
    restart: unless-stopped
    mem_limit: 1g

  hermes:
    image: nousresearch/hermes-agent:latest
    environment:
      - LLM_BACKEND_URL=http://velum:8000/v1
    depends_on:
      - velum
```

```bash
# Start
docker compose up -d

# View logs
docker logs -f velum
```

### Client Configuration

Point your LLM client to `http://your-host:8000/v1`. The API key is your upstream LLM key (Velum proxies it, never stores it).

| Client | Where to configure |
|--------|-------------------|
| CherryStudio | Settings → Model Services → API URL |
| Hermes | Env var `LLM_BACKEND_URL` |
| OpenAI SDK | `base_url="http://your-host:8000/v1"` |

## Mode Switching

Prepend `!pii` to your message to **temporarily** switch the redaction mode for that message. The next message without a prefix automatically returns to the default identifier mode. Both full-width `！` and half-width `!` are accepted.

| Command | Effect |
|---------|--------|
| `!pii` | Show firewall status and strategy configuration |
| `!pii debug <text>` | Analyze what PII would be detected in the text (no LLM call) |
| `!pii 伪名` / `!pii pseudonym` | Pseudonym mode for this message (realistic fake names) |
| `!pii org,loc` | Partial override for this message: keep organization and location |

### Example: Temporary Pseudonym Mode

```
User: !pii pseudonym Look up Zhang Wei's contact info
      → This message sent in pseudonym mode. LLM sees fake names.
      → Response restored with real names before display.

User: Now look up Li Na's   ← No prefix — auto-returns to identifier mode
      → Normal redaction with per-type prefixes
```

### Example: Debug Analysis

```
User: !pii debug Li Ming works at Xiong'an New Area, phone 13900001111

Original: Li Ming works at Xiong'an New Area, phone 13900001111
Redacted: P-47141 works at P-72185, phone T-39281
Entities: 3

Detected:
  [1] person  Li Ming → P-47141
  [1] person  Xiong'an New Area → P-72185
  [1] phone   13900001111 → T-39281

User: Help me summarize   ← Next message — normal conversation
```

## Redaction Strategies

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

## Compound Location Enhancement

HanLP's Chinese NER model has blind spots for economic zones with non-standard administrative suffixes (e.g., "成都天府新区", "雄安新区") — they are classified as neither ORG nor LOC, passing through undetected.

Velum includes 430+ compound location names (national new districts, economic development zones, high-tech zones, free trade zones) injected via argus-redact's `names` parameter at Layer 1 regex matching. The name list is maintained as a plain text file (`location_names.txt`) — no code changes needed to add or remove entries.

## Architecture

```
main.py (~620 lines)
├── /health                   Health check
├── /v1/models                Model list (proxied upstream)
├── /v1/chat/completions      OpenAI-compatible endpoint
│   ├── get_last_user_content  Extract last user message
│   ├── parse_mode_prefix      Parse !pii mode prefix
│   ├── redact_text            Call argus-redact for PII redaction
│   ├── [Upstream LLM call]
│   ├── restore_text           Restore PII in LLM response
│   └── SSE buffer-restore     DeepSeek streaming response handling
│
├── location_names.txt         Compound location names (430+ entries)
├── test_strategies.py         Strategy config integration tests
└── test_custom_dict.py        names parameter + compound location tests
```

### PII Pipeline

```
User Message → parse_mode_prefix() → Mode Detection
             → redact_text() → argus-redact redact()
                   ├─ Layer 1: regex (names parameter)
                   └─ Layer 2: HanLP cascaded NER
             → Redacted Message → Upstream LLM
             → LLM Response → restore_text() → Restore PII → User
```

### SSE Streaming

DeepSeek's SSE stream splits identifiers across chunks (e.g., `P-00` + `128`), making per-chunk restoration impossible. Velum uses a **buffer-concat-restore** strategy: cache all SSE chunks → concatenate full text → restore PII → repack as single SSE event.

## Limitations

1. **`names` entities classified as `person`**: argus-redact's Layer 1 regex bypasses the NER classification pipeline, defaulting to person type. Does not affect privacy — per-type prefixes distinguish entity types, and `detailed=True` exposes type information.
2. **Standard administrative names still rely on NER**: Locations with standard suffixes (e.g., "海淀区卫健委") are covered by HanLP NER, not the `names` list.
3. **Short text NER may fail**: Inputs under 8 characters lack sufficient context for HanLP segmentation.
4. **money entity out of scope**: argus-redact's 56-type catalog does not include money; RMB amounts are not redacted.
5. **Transparent proxy, not encrypted transport**: If your upstream LLM API uses HTTP, messages travel in plaintext on the wire.

## argus-redact Engine

Velum delegates all PII detection to argus-redact, which uses a **three-layer progressive architecture**:

| Layer | Mechanism | Coverage |
|-------|-----------|----------|
| **Layer 1: Regex** | Rule-based regex for format-constrained PII (phone numbers, ID numbers, emails, bank cards) + `names` parameter for custom entity injection | Format-fixed PII + custom dictionaries |
| **Layer 2: Cascaded NER** | HanLP 2.x Chinese NER. Recognition order: person → location → organization (cascaded dependency) | Person, location, organization, school, date, etc. |
| **Layer 3: Semantic/LLM** | Reserved interface for context-dependent PII (currently disabled) | — |

### HanLP Model Stack

| Component | Details |
|-----------|---------|
| **Encoder** | ELECTRA-small (12-layer Transformer, ~14M params) |
| **NER Decoder** | Biaffine NER (treats NER as dependency parsing, natively supports nested/flat entities) |
| **Training Data** | MSRA (largest Chinese NER corpus) + OntoNotes 4.0 Chinese |
| **Entity Types** | 56 categories (PER/LOC/ORG/GPE/FAC/VEH/...) |
| **Annotation Scheme** | PKU standard: person(nr) → location(ns) → organization(NT), cascaded labeling |

> **Key insight**: Biaffine NER makes no flat-entity assumption — in `[北京/ns 大学/n]NT`, "北京" is simultaneously an independent location entity AND part of an organization phrase. This span-based approach natively handles compound entities.

## Agent Integration Guide

### CherryStudio

1. Settings → Model Services → Add Provider
2. API URL: `http://your-host:8000/v1`
3. API Key: your upstream LLM API key (Velum proxies it, never stores it)
4. Model list syncs automatically from upstream

### Hermes Gateway

Point Hermes to Velum as the LLM backend:

```yaml
# Hermes environment variable
LLM_BACKEND_URL=http://velum:8000/v1
```

> **Note**: Hermes intercepts all `/`-prefixed commands at the gateway level. Velum uses `!pii` prefix — unaffected. Do NOT use `/pii`.

### Any OpenAI SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://your-host:8000/v1",
    api_key="your-upstream-api-key",
)

# Normal usage — PII is automatically redacted
response = client.chat.completions.create(
    model="your-model",
    messages=[{"role": "user", "content": "!pii debug test text"}],
)
```

### WeChat (via Hermes WeChat Adapter)

Hermes includes a built-in WeChat adapter. Message flow: WeChat → Hermes Gateway → Velum → Upstream LLM → back. Chat normally in WeChat; `!pii` commands are typed directly in the chat box.

## Test Environment

| Component | Version / Notes |
|-----------|----------------|
| **Runtime** | Synology NAS (DSM 7.x) · Docker 24+ |
| **Python** | 3.12-slim |
| **argus-redact** | ≥ 0.5.0 (with HanLP Chinese NER) |
| **Gateway** | Hermes Agent (nousresearch/hermes-agent:latest) |
| **Clients** | WeChat (via Hermes adapter) · CherryStudio · Any OpenAI SDK |
| **Upstream LLM** | DeepSeek V4 Pro |
| **Memory** | < 500MB (including HanLP model) |

### Suitable For

- ✅ Personal LLM use via IM gateways (WeChat, Telegram, Web)
- ✅ Internal enterprise LLM proxy with unified PII policy
- ✅ Any OpenAI-compatible API upstream
- ⚠️ High-concurrency production needs load balancing (single-instance by default)
- ❌ Environments requiring full SOC2/HIPAA compliance (this is a technical tool, not a certified compliance solution)

## License

MIT

---

[中文文档](README.md)
