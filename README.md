# PaperForGeoAgent — GEO 论文追踪智能体

**Generative Engine Optimization（生成式引擎优化）** 领域的学术论文自动追踪系统。

每日自动从 arXiv 抓取最新论文，通过 LangGraph 多 Agent 流水线完成：
1. **抓取** → arXiv API（cs.IR, cs.CL, cs.AI, cs.CY, cs.HC），智能回退找最近有论文的日期
2. **筛选** → Agent A：LLM 相关性评分（1-5分）+ 反思校验，飞书卡片内渐进更新进度
3. **梗概** → Agent B：结构化中文梗概生成，卡片内实时显示
4. **存储** → SQLite（去重 + 断点恢复）+ Chroma（向量知识库）
5. **输出** → 飞书 Interactive Card 日报 / 文本摘要

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置

```bash
cp .env.example .env
# 编辑 .env 填入火山引擎 Ark API Key 和飞书应用凭证
```

必填项：

| 变量 | 说明 |
|------|------|
| `ARK_API_KEY` | 火山引擎 Ark API Key |
| `ARK_MODEL_ID` | 模型 ID（推荐 `doubao-1-5-pro-32k-250115`） |
| `FEISHU_APP_ID` | 飞书应用 App ID |
| `FEISHU_APP_SECRET` | 飞书应用 App Secret |

可选项：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `FEISHU_RECEIVE_ID` | 空 | 定时调度时的推送目标（open_id 或 chat_id） |
| `FEISHU_RECEIVE_ID_TYPE` | `open_id` | `open_id`（私聊）或 `chat_id`（群聊） |
| `SCHEDULE_TIME` | `08:00` | 每日推送时间（北京时间） |
| `FILTER_MIN_SCORE` | `3` | 论文筛选最低分 |
| `FILTER_TOP_K` | `5` | 深度梗概篇数 |
| `ARXIV_DAYS_BACK` | `1` | arXiv 回溯天数 |

### 3. 启动飞书机器人

飞书长连接模式（推荐，无需内网穿透）：

```bash
python -m src.ws_server
```

启动后在群里 @机器人 即可触发流水线。

Webhook 模式（需公网）：

```bash
python -m src.webhook_server
```

### 4. 飞书操作

| 对话 | 效果 |
|------|------|
| `最近有什么新论文` | 自动找最近有论文的日期，推送日报 |
| `今天有什么论文` | 推送今日论文 |
| `上周五有什么新论文` | 推送指定日期论文（支持相对日期） |
| `推送昨天` | 推送昨天论文 |
| `搜索 RAG优化` | 从向量知识库搜索 |
| `帮助` | 查看所有可用操作 |

### 5. 命令行模式

```bash
# 手动触发一次
python -m src.main --run

# 指定日期
python -m src.main --run --date 2026-07-03

# 启动每日定时调度
python -m src.main --schedule

# 搜索知识库
python -m src.main --search "RAG 优化"

# 查看飞书可用群聊/用户
python -m src.main --list-chats
python -m src.main --list-users
```

## 飞书卡片体验

流水线执行时，只发送**一张卡片**，内容随流程渐进更新：

```
[卡片] 🔍 GEO 论文筛选中 | 2026-07-02
       📡 抓取完成: 222 篇论文
       ✅ 批次 1/23: 9 篇 → 通过 2 篇
       ✅ 批次 2/23: 10 篇 → 通过 1 篇
       ...
       ✅ 筛选完成: 15/222 篇通过
       ...
       📝 正在生成梗概...
       ✅ [1/5] 评估学术文本的分块策略
       ✅ [2/5] 了解信息源：公共知识库
       ...
```

最终转为精美日报卡片。

## 断点恢复

每批 LLM 筛选结果实时保存到 SQLite。如果流程中断（如 LLM 超时、网络故障），重新触发相同日期时自动跳过已完成批次，从断点继续。

## 项目结构

```
src/
├── main.py           # CLI 入口 + 定时调度
├── config.py          # 配置中心
├── state.py           # LangGraph 状态定义
├── graph.py           # LangGraph 图编排（条件路由）
├── webhook_server.py  # 飞书 Webhook 服务（Flask）
├── ws_server.py       # 飞书长连接服务（WebSocket）
├── nodes/             # Agent 节点
│   ├── fetch.py       # arXiv 抓取（429 重试）
│   ├── filter.py      # Agent A: LLM 筛选 + 断点恢复 + 卡片渐进
│   ├── reflect.py     # 反思校验（二次评估）
│   ├── digest.py      # Agent B: 中文梗概 + 卡片渐进
│   ├── store.py       # SQLite + Chroma 持久化
│   └── output.py      # 日报生成 + 飞书卡片推送
├── models/            # 数据模型 + LLM 客户端
├── storage/           # SQLite（含断点表）+ Chroma
└── utils/
    ├── logger.py       # 日志（UTF-8 / Windows 兼容）
    └── feishu.py       # 飞书 API（Token、消息、卡片、更新）
```

## 技术栈

- **Agent 框架**: LangGraph
- **大模型**: 豆包（火山引擎 Ark API，OpenAI 兼容）
- **数据库**: SQLite + Chroma（all-MiniLM-L6-v2 embedding）
- **论文源**: arXiv API（`arxiv` 库，429 指数退避重试）
- **消息**: 飞书长连接（WebSocket）+ Interactive Card + PATCH 更新
