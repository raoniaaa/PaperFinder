"""论文数据模型。"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Paper:
    """arXiv 原始论文数据。"""
    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    published_date: str
    pdf_url: str
    primary_category: str
    relevance_score: int = 0   # Agent A 打分 (1-5)
    relevance_reason: str = ""  # Agent A 打分理由


@dataclass
class DigestedPaper:
    """经过 Agent B 深度处理后的论文。"""
    paper: Paper
    chinese_title: str
    one_line_contribution: str   # 一句话核心贡献
    methodology: str              # 主要方法论
    experiment_results: str       # 实验与结果
    geo_insight: str              # 对 GEO 领域的启发
