# PaperForGeoAgent — GEO 论文追踪智能体

**Generative Engine Optimization（生成式引擎优化）** 领域的学术论文自动追踪系统。

每日自动从 arXiv 抓取最新论文，通过 LangGraph 多 Agent 流水线完成：
1. **抓取** → arXiv API（cs.IR, cs.CL, cs.AI, cs.CY, cs.HC）
2. **筛选** → Agent A：LLM 相关性评分（1-5分）
3. **梗概** → Agent B：结构化中文梗概生成
4. **存储** → SQLite（去重）+ Chroma（向量知识库）
5. **输出** → 终端日报 + 飞书卡片数据结构

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置

```bash
cp .env.example .env
# 编辑 .env 填入你的火山引擎 Ark API Key
```

### 3. 运行

```bash
# 手动运行一次
python -m src.main --run

# 启动每日定时调度
python -m src.main --schedule

# 搜索知识库
python -m src.main --search "RAG 优化"
```

## 项目结构

```
src/
├── main.py           # CLI 入口
├── config.py          # 配置中心
├── state.py           # LangGraph 状态定义
├── graph.py           # LangGraph 图编排
├── nodes/             # Agent 节点
│   ├── fetch.py       # arXiv 抓取
│   ├── filter.py      # Agent A: 筛选
│   ├── digest.py      # Agent B: 梗概
│   ├── store.py       # 存储
│   └── output.py      # 输出
├── models/            # 数据模型 + LLM 客户端
├── storage/           # SQLite + Chroma
└── utils/             # 日志
```

## 技术栈

- **Agent 框架**: LangGraph
- **大模型**: 豆包（火山引擎 Ark API）
- **数据库**: SQLite + Chroma
- **论文源**: arXiv API (`arxiv` 库)
- **调度**: `schedule` 库
