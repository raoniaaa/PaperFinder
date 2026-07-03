"""项目配置中心。"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# --- 项目根目录 ---
PROJECT_ROOT = Path(__file__).parent.parent

# --- 豆包 / 火山引擎 Ark API ---
ARK_API_KEY = os.getenv("ARK_API_KEY", "")
ARK_BASE_URL = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
ARK_MODEL_ID = os.getenv("ARK_MODEL_ID", "doubao-pro-32k")

# --- arXiv 抓取配置 ---
ARXIV_CATEGORIES = [
    "cs.IR",   # Information Retrieval
    "cs.CL",   # Computation and Language
    "cs.AI",   # Artificial Intelligence
    "cs.CY",   # Computers and Society
    "cs.HC",   # Human-Computer Interaction
]
ARXIV_MAX_RESULTS_PER_CATEGORY = int(os.getenv("ARXIV_MAX_RESULTS_PER_CATEGORY", "50"))
ARXIV_DAYS_BACK = int(os.getenv("ARXIV_DAYS_BACK", "1"))

# --- 筛选配置 ---
FILTER_BATCH_SIZE = 10
FILTER_MIN_SCORE = int(os.getenv("FILTER_MIN_SCORE", "3"))
FILTER_TOP_K = int(os.getenv("FILTER_TOP_K", "5"))

# GEO 领域关键词矩阵
GEO_HIGH_PRIORITY_KEYWORDS = [
    "generative engine optimization",
    "answer engine optimization",
    "AI search engine",
    "AI-powered search",
    "conversational search",
    "large language model search",
    "LLM search ranking",
    "retrieval augmented generation",
    "RAG optimization",
]

GEO_MEDIUM_PRIORITY_KEYWORDS = [
    "citation reliability",
    "LLM attribution",
    "hallucination mitigation",
    "information retrieval",
    "AI overviews",
    "search result bias",
    "content visibility",
    "structured data",
    "search engine optimization",
    "SEO",
    "generative AI search",
    "AI-generated answers",
    "source attribution",
    "search result fairness",
    "ranking algorithm",
]

GEO_NEGATIVE_KEYWORDS = [
    "medical image",
    "face recognition",
    "autonomous driving",
    "medical imaging",
    "clinical",
    "radiology",
]

# --- 存储配置 ---
DATA_DIR = PROJECT_ROOT / "data"
SQLITE_DB_PATH = DATA_DIR / "papers.db"
CHROMA_PERSIST_DIR = str(DATA_DIR / "chroma_db")

# --- 定时调度 ---
SCHEDULE_TIME = os.getenv("SCHEDULE_TIME", "08:00")

# --- 日志配置 ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = DATA_DIR / "agent.log"

# 确保数据目录存在
DATA_DIR.mkdir(parents=True, exist_ok=True)
