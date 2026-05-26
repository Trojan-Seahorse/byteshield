# Velum · LLM 隐私防火墙

**透明代理层，在消息到达 LLM 之前自动检测并脱敏个人身份信息（PII），响应返回后还原。**

```
用户 → Hermes/任意客户端 → [Velum PII 防火墙] → LLM API
                              ↑
                    脱敏后转发 → 响应还原 → 用户
```

## 为什么需要

LLM API 是黑盒——你的对话内容会被服务商记录、存储、用于模型训练。直接发送含真实姓名、电话、身份证号、地址等信息的消息，等同于把这些数据交给第三方。

Velum 在你的消息离开内网之前拦截 PII，替换为不可逆的匿名标识符（如 `P-00128`、`L-23017`），LLM 永远看不到原始数据。响应返回时自动还原，用户无感知。

## 核心特性

| 特性 | 说明 |
|------|------|
| **透明代理** | OpenAI 兼容 API 端点，客户端只需改 URL |
| **多模式切换** | 消息内 `!pii` 前缀即可切换脱敏策略，无需修改配置 |
| **分类型标识** | 每种实体类型使用不同前缀（P-人名 O-组织 L-地点 T-电话...），LLM 可区分实体类型 |
| **SSE 流式还原** | DeepSeek reasoning_content 也完整还原 |
| **复合地名增强** | 内建 430+ 经济功能区地名（园区/新区/经开区等），弥补 HanLP NER 盲区 |
| **Fail-open** | 脱敏引擎异常时直通原文，不阻断服务 |
| **低依赖** | 仅依赖 argus-redact + FastAPI，单容器运行，内存 < 500MB |

## 环境要求

| 条件 | 说明 |
|------|------|
| Docker | 24+，含 docker compose |
| LLM API | 任意 OpenAI 兼容 API（DMXAPI、OpenAI 等） |
| Python | 3.12（仅开发/测试需要，部署用 Docker） |
| 内存 | ≥ 1GB（含 HanLP 模型 ~400MB） |

## 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/Trojan-Seahorse/velum.git
cd velum

# 2. 构建镜像
docker build -t velum .

# 3. 启动容器
docker run -d -p 8000:8000 \
  -e UPSTREAM_URL=https://your-llm-api.com/v1 \
  -e ARGUS_REDACT_PSEUDONYM_SALT=$(openssl rand -hex 16) \
  --name velum velum

# 4. 验证连通性
curl http://localhost:8000/health
# → {"status": "ok", "pii_enabled": true}

# 5. 测试 PII 脱敏
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-api-key" \
  -d '{
    "model": "deepseek-chat",
    "messages": [
      {"role": "user", "content": "!pii debug 张伟的电话是13900001111"}
    ],
    "stream": true
  }'
```

> **提示**：第 3 步的 `UPSTREAM_URL` 指向你的 LLM API 地址。`ARGUS_REDACT_PSEUDONYM_SALT` 用于化名模式的确定性生成，请使用随机字符串。

### Docker Compose（配合 Hermes 网关）

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
# 启动
docker compose up -d

# 查看日志
docker logs -f velum
```

### 客户端配置

将 LLM 客户端的 API 地址指向 `http://your-host:8000/v1`，API Key 填写上游 LLM 的 Key（Velum 透传，不存储）。

| 客户端 | 配置位置 |
|--------|---------|
| CherryStudio | 设置 → 模型服务 → API 地址 |
| Hermes | 环境变量 `LLM_BACKEND_URL` |
| OpenAI SDK | `base_url="http://your-host:8000/v1"` |

## 模式切换

在对话消息开头加上 `!pii` 前缀即可**临时**切换本条消息的脱敏模式。下一条消息不加前缀则自动恢复默认标识符模式。全角 `！` 和半角 `!` 均支持。

| 命令 | 效果 |
|------|------|
| `!pii` | 查看当前防火墙状态和策略配置 |
| `!pii debug <文本>` | 分析指定文本会被检测出哪些 PII，不调用 LLM |
| `!pii 伪名` | 本条消息使用化名模式（人名替换为逼真假名） |
| `!pii org,loc` | 本条消息部分放行：保留组织和地名不脱敏 |

### 示例：临时伪名模式

```
用户: !pii 伪名 帮我查一下张伟的通讯录信息
      ↓ 本条消息以化名模式发送，LLM 看到的是 "帮我查一下刘建国的通讯录信息"
      ↓ LLM 回复后自动还原真实姓名

用户: 再帮我查一下李娜的   ← 不加前缀，自动恢复默认标识符模式
      ↓ 本条消息正常脱敏为 per-type 前缀
```

### 示例：调试分析

```
用户: !pii debug 李明在成都天府新区管委会工作，电话13900001111

原文: 李明在成都天府新区管委会工作，电话13900001111
脱敏: P-47141在P-72185管委会工作，电话T-39281
实体数: 3

检测到的实体:
  [1] person  李明 → P-47141
  [1] person  成都天府新区 → P-72185
  [1] phone   13900001111 → T-39281

用户: 帮我总结一下   ← 下一条消息正常对话
```

## 脱敏策略

| 实体类型 | 策略 | 示例 |
|---------|------|------|
| 人名 (person) | remove | 李明 → P-00128 |
| 组织 (organization) | remove | 阿里巴巴 → O-09502 |
| 学校 (school) | remove | 浙江大学 → S-14439 |
| 地点 (location) | remove | 北京市 → L-23017 |
| 电话 (phone) | remove | 13900001111 → T-39281 |
| 邮箱 (email) | remove | a@b.com → E-55612 |
| 身份证 (id_number) | remove | 110101... → I-78403 |
| 地址 (address) | remove | 天府大道200号 → A-66194 |
| 银行卡 (bank_card) | mask | 622202... → ****0123 |
| 自称 (self_reference) | keep | 不处理 |
| 日期 (date) | remove | 2024-03-15 → D-33501 |

## 复合地名增强

HanLP 中文 NER 模型对"成都天府新区""雄安新区"等非标准行政后缀的经济功能区存在识别盲区——它们既不被分类为 ORG（组织），也不被分类为 LOC（地点），导致直接放行。

Velum 内建了 430+ 复合地名列表（国家级新区、经开区、高新区、自贸区等），通过 argus-redact 的 `names` 参数注入 Layer 1 正则匹配层，强制检测。地名列表以纯文本文件 `location_names.txt` 维护，增删无需改代码。

## 架构

```
main.py (620 行)
├── /health                   健康检查
├── /v1/models                模型列表（转发上游）
├── /v1/chat/completions      OpenAI 兼容端点
│   ├── get_last_user_content  提取最后一条用户消息
│   ├── parse_mode_prefix      解析 !pii 模式前缀
│   ├── redact_text            调用 argus-redact 脱敏
│   ├── [上游 LLM 调用]
│   ├── restore_text           还原 LLM 响应中的 PII
│   └── SSE 流式缓冲还原       DeepSeek 流式响应处理
│
├── location_names.txt         复合地名列表（430+ 条目）
├── test_strategies.py         策略配置集成测试
└── test_custom_dict.py        names 参数 + 复合地名测试
```

### PII 处理流程

```
用户消息 → parse_mode_prefix() → 识别模式
         → redact_text() → argus-redact redact()
               ├─ Layer 1: regex (names 参数)
               └─ Layer 2: HanLP cascaded NER
         → 脱敏后消息 → 上游 LLM
         → LLM 响应 → restore_text() → 还原 PII → 返回用户
```

### SSE 流式处理

DeepSeek 的 SSE 流会将标识符分散在多个 chunk 中（如 `P-00` + `128`），无法逐 chunk 还原。Velum 采用**缓冲-拼接-还原**策略：将所有 SSE chunk 缓存 → 拼接完整文本 → 还原 PII → 打包为单个 SSE 事件返回。

## 限制与已知问题

1. **`names` 参数实体归为 person 类型**：argus-redact 的 Layer 1 正则匹配不经过 NER 分类管线，默认标记为 person。不影响隐私保护——per-type 前缀已按实体类型区分，`detailed=True` 可获取类型信息。
2. **标准行政地名仍依赖 NER**：海淀区卫健委、江苏省人民医院等标准后缀地名由 HanLP NER 覆盖，不在 `names` 列表中。
3. **短文本 NER 可能失效**：少于 8 个字符的输入，HanLP 分词上下文不足，可能漏检。
4. **money 实体不在范围内**：argus-redact 的 56 类实体目录不含 money，人民币金额不脱敏。
5. **透明代理，非加密信道**：如果你的上游 LLM API 使用 HTTP，消息在网络传输中仍然是明文的。

## argus-redact 引擎详解

Velum 的 PII 检测完全委托给 argus-redact。它采用**三层递进架构**：

| 层级 | 机制 | 覆盖范围 |
|------|------|---------|
| **Layer 1: 正则匹配** | 基于规则的正则表达式，匹配手机号、身份证号、邮箱、银行卡号等格式明确的 PII；同时承载 `names` 参数注入的自定义实体 | 格式明确的 PII + 自定义词典 |
| **Layer 2: 级联 NER** | HanLP 2.x 中文命名实体识别。先识别人名 → 地名 → 再基于此识别机构名（级联依赖） | 人名、地名、机构名、学校、日期等 |
| **Layer 3: 语义/LLM** | 保留接口，用于处理语境依赖的 PII（当前未启用） | — |

### HanLP 模型

Velum 使用的 HanLP 2.x 模型栈：

| 组件 | 说明 |
|------|------|
| **编码器** | ELECTRA-small（12 层 Transformer，参数量 ~14M） |
| **NER 解码器** | Biaffine NER（将 NER 作为依存分析任务，自然支持 nested/flat 实体） |
| **训练语料** | MSRA（最大中文 NER 语料库）+ OntoNotes 4.0 中文部分 |
| **实体类型** | 56 类（PER/LOC/ORG/GPE/FAC/VEH/...） |
| **标注规范** | PKU 标注集：人名(nr) → 地名(ns) → 机构名(NT)，级联标注 |

> **关键特性**：Biaffine NER 不假设实体扁平——`[北京/ns 大学/n]NT` 中的"北京"既是独立地名实体又是机构名短语的一部分。这种 span-based 方法天然处理复合实体。

## Agent 集成指南

### CherryStudio

1. 设置 → 模型服务 → 添加提供商
2. API 地址：`http://your-host:8000/v1`
3. API Key：填写上游 LLM 的 API Key（Velum 仅透传，不存储）
4. 模型列表自动从上游同步

### Hermes 网关

在 Hermes 配置中将 LLM 后端地址指向 Velum：

```yaml
# Hermes 环境变量
LLM_BACKEND_URL=http://velum:8000/v1
```

> **注意**：Hermes 在网关层拦截所有 `/` 开头的命令。Velum 使用 `!pii` 前缀不受影响。不要使用 `/pii`。

### 任意 OpenAI SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://your-host:8000/v1",
    api_key="your-upstream-api-key",
)

# 正常使用，PII 自动脱敏
response = client.chat.completions.create(
    model="your-model",
    messages=[{"role": "user", "content": "!pii debug 测试文本"}],
)
```

### 微信接入（via Hermes WeChat Adapter）

Hermes 内置 WeChat adapter，微信消息 → Hermes 网关 → Velum → 上游 LLM → 原路返回。用户在微信中正常对话即可，`!pii` 命令直接在聊天框输入。

## 测试环境

| 组件 | 版本/说明 |
|------|---------|
| **运行环境** | Synology NAS (DSM 7.x) · Docker 24+ |
| **Python** | 3.12-slim |
| **argus-redact** | ≥ 0.5.0 (with HanLP Chinese NER) |
| **网关** | Hermes Agent (nousresearch/hermes-agent:latest) |
| **客户端** | 微信 (via Hermes WeChat adapter) · CherryStudio · 任意 OpenAI SDK |
| **上游 LLM** | DeepSeek V4 Pro (via DMXAPI) |
| **内存占用** | < 500MB（含 HanLP 模型） |

### 适用场景

- ✅ 个人 LLM 使用，通过微信/Telegram/Web 等 IM 网关访问
- ✅ 企业内部 LLM 代理，统一 PII 策略
- ✅ 任何 OpenAI 兼容 API 的上游
- ⚠️ 高并发生产环境需加负载均衡（当前为单实例）
- ❌ 需要完整 SOC2/HIPAA 合规的场景（此为技术工具，非认证合规方案）

## 许可证

MIT
