"""存储层: SQLite（去重） + Chroma（向量知识库）。"""

import sqlite3
from pathlib import Path
from src.config import SQLITE_DB_PATH, DATA_DIR


class PaperStore:
    """SQLite 存储 —— 已读论文去重与记录。"""

    def __init__(self, db_path: Path = SQLITE_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """初始化数据库表。"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS papers (
                    arxiv_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    authors TEXT,
                    abstract TEXT,
                    published_date TEXT,
                    pdf_url TEXT,
                    primary_category TEXT,
                    relevance_score INTEGER DEFAULT 0,
                    chinese_title TEXT,
                    one_line_contribution TEXT,
                    methodology TEXT,
                    experiment_results TEXT,
                    geo_insight TEXT,
                    created_at TEXT DEFAULT (datetime('now', 'localtime'))
                )
            """)
            conn.commit()

    def exists(self, arxiv_id: str) -> bool:
        """检查论文是否已存在。"""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute(
                "SELECT 1 FROM papers WHERE arxiv_id = ?", (arxiv_id,)
            )
            return cursor.fetchone() is not None

    def insert_paper(self, digested) -> bool:
        """插入一篇论文记录，返回是否插入成功（去重）。"""
        from src.models.paper import DigestedPaper
        p = digested.paper
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO papers
                    (arxiv_id, title, authors, abstract, published_date, pdf_url,
                     primary_category, relevance_score, chinese_title,
                     one_line_contribution, methodology, experiment_results, geo_insight)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        p.arxiv_id,
                        p.title,
                        ", ".join(p.authors),
                        p.abstract,
                        p.published_date,
                        p.pdf_url,
                        p.primary_category,
                        p.relevance_score,
                        digested.chinese_title,
                        digested.one_line_contribution,
                        digested.methodology,
                        digested.experiment_results,
                        digested.geo_insight,
                    ),
                )
                conn.commit()
                return conn.total_changes > 0
        except Exception as e:
            import logging
            logging.getLogger("geo_agent").error(f"SQLite 写入失败 [{p.arxiv_id}]: {e}")
            return False

    def get_recent_ids(self, days: int = 30) -> set[str]:
        """获取最近 N 天内已存的 arxiv_id。"""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute(
                """
                SELECT arxiv_id FROM papers
                WHERE created_at >= datetime('now', 'localtime', ?)
                """,
                (f"-{days} days",),
            )
            return {row[0] for row in cursor.fetchall()}

    def get_by_date(self, published_date: str) -> list[dict]:
        """按发布日期获取已存入的论文及梗概数据。

        Returns:
            list[dict] 每篇包含完整字段，可直接用于构建日报和飞书卡片。
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute(
                """
                SELECT arxiv_id, title, authors, abstract, published_date,
                       pdf_url, primary_category, relevance_score,
                       chinese_title, one_line_contribution, methodology,
                       experiment_results, geo_insight
                FROM papers WHERE published_date = ?
                ORDER BY relevance_score DESC
                """,
                (published_date,),
            )
            rows = cursor.fetchall()
            if not rows:
                return []

            results = []
            from src.models.paper import Paper, DigestedPaper

            for row in rows:
                p = Paper(
                    arxiv_id=row[0],
                    title=row[1],
                    authors=row[2].split(", ") if row[2] else [],
                    abstract=row[3] or "",
                    published_date=row[4] or "",
                    pdf_url=row[5] or "",
                    primary_category=row[6] or "",
                )
                p.relevance_score = row[7] or 0
                dp = DigestedPaper(
                    paper=p,
                    chinese_title=row[8] or "",
                    one_line_contribution=row[9] or "",
                    methodology=row[10] or "",
                    experiment_results=row[11] or "",
                    geo_insight=row[12] or "",
                )
                results.append(dp)
            return results


# 全局单例
paper_store = PaperStore()
