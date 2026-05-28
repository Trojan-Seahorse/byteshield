# Velum · LLM 隐私防火墙

透明代理层，在消息到达 LLM 之前自动检测并脱敏个人信息，响应返回后还原。LLM 永远看不到原始数据。

```
用户 → 任意客户端 → [Velum] → LLM API
                      ↑
            脱敏后转发 → 响应还原 → 用户
```

## 环境要求

| 条件 | 说明 |
|------|------|
| Docker | 24+，含 docker compose |
| 上游 LLM API | 任意 OpenAI 兼容 API（DMXAPI、OpenAI 等） |
| 内存 | ≥ 1GB（含 HanLP 模型 ~400MB） |

## 部署

### 方式一：Docker 单容器

```bash
git clone https://github.com/Trojan-Seahorse/velum.git
cd velum
docker build -t velum .
docker run -d -p 8000:8000 \
  -e UPSTREAM_URL=https://your-llm-api.com/v1 \
  -e ARGUS_REDACT_PSEUDONYM_SALT=$(openssl rand -hex 16) \
  --name velum velum
```

验证：

```bash
curl http://localhost:8000/health
# → {"status":"ok","upstream":"https://your-llm-api.com/v1","pii":"ok"}
```

### 方式二：Docker Compose（配合 Hermes 网关）

```yaml
# docker-compose.yml（放在 velum 仓库根目录）
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

> **注意**：Hermes 的 LLM 后端地址需要在 `./hermes/config.yaml` 和 `./hermes/auth.json` 中配置为 `http://velum:8000/v1`，不是环境变量。

```bash
# 创建 Hermes 数据目录和配置
mkdir -p hermes
# 编辑 ./hermes/config.yaml，设置 base_url: http://velum:8000/v1
# 编辑 ./hermes/auth.json，设置 base_url: http://velum:8000/v1

docker compose up -d
docker logs -f velum
```

### 客户端配置

将客户端的 API 地址指向 Velum，API Key 填写上游 LLM 的 Key（Velum 透传，不存储）。

| 客户端 | 配置方式 |
|--------|---------|
| CherryStudio | 设置 → 模型服务 → API 地址: `http://your-host:17829/v1` |
| Hermes | `config.yaml` + `auth.json`: `base_url: http://velum:8000/v1` |
| OpenAI SDK | `base_url="http://your-host:8000/v1"` |

## 日常使用

对话开头加 `!pii` 前缀即可切换脱敏模式，不加前缀使用默认策略。全角 `！` 和半角 `!` 均支持。

| 命令 | 效果 |
|------|------|
| `!pii` | 查看当前防火墙状态和策略 |
| `!pii debug <文本>` | 分析 PII 检测结果，不调用 LLM |
| `!pii 伪名` | 人名替换为逼真假名（其他类型照常脱敏） |
| `!pii org,loc` | 保留组织和地名不脱敏 |

示例：

```
用户: !pii debug 张伟在苏州工业园区管委会工作，电话13900001111

原文: 张伟在苏州工业园区管委会工作，电话13900001111
脱敏: P-47141在P-72185管委会工作，电话T-39281
实体数: 3

检测到的实体:
  [1] person  张伟 → P-47141
  [2] person  苏州工业园区 → P-72185
  [3] phone   13900001111 → T-39281

用户: 帮我总结一下   ← 下一条消息不加前缀，恢复正常脱敏模式
```

### 脱敏策略

| 类型 | 策略 | 示例 |
|------|------|------|
| 人名 | remove | 李明 → P-00128 |
| 组织 | remove | 阿里巴巴 → O-09502 |
| 学校 | remove | 浙江大学 → S-14439 |
| 地点 | remove | 北京市 → L-23017 |
| 电话 | remove | 13900001111 → T-39281 |
| 邮箱 | remove | a@b.com → E-55612 |
| 身份证 | remove | 110101... → I-78403 |
| 地址 | remove | 天府大道200号 → A-66194 |
| 银行卡 | mask | 622202... → ****0123 |
| 自称 | keep | 不处理 |
| 日期 | remove | 2024-03-15 → D-33501 |

## 环境变量

| 变量 | 必填 | 说明 |
|------|:----:|------|
| `UPSTREAM_URL` | ✅ | 上游 LLM API 地址，如 `https://www.dmxapi.cn/v1` |
| `ARGUS_REDACT_PSEUDONYM_SALT` | ✅ | 化名模式的盐值，用随机字符串 |
| `PII_ENABLED` | — | 设为 `false` 关闭脱敏（默认 `true`） |

## 故障排查

### `/health` 返回 `pii: error`

HanLP 模型下载失败。检查容器网络，手动预热：

```bash
docker exec velum python -c "from argus_redact import redact; redact('测试', lang='zh')"
```

### `!pii debug` 显示漏检

短文本（< 8 字符）或非标准行政后缀的地名（如 "苏州工业园区"）可能被 NER 漏检。这是 HanLP 模型的已知局限。

- **临时方案**：用 `!pii 伪名` 切换到化名模式
- **永久方案**：在 `location_names.txt` 中添加漏检地名，重启容器

### 上游 LLM 连接超时

```bash
# 确认环境变量
docker exec velum env | grep UPSTREAM_URL

# 确认容器能连通上游
docker exec velum python -c "import httpx; r = httpx.get('$UPSTREAM_URL/models'); print(r.status_code)"
```

### 容器 OOM

HanLP 模型约 400MB，构建时预下载。运行时建议 ≥ 1GB：

```bash
docker run --memory=1g ...          # 单容器
mem_limit: 1g                        # docker compose
```

## 许可证

MIT
