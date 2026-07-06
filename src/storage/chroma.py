"""Chroma 向量存储 —— GEO 知识库语义搜索。"""

import os

# 将 Hugging Face / Sentence Transformers 模型缓存指向 D 盘
os.environ.setdefault("HF_HOME", "D:\\chroma_embedding_models")
os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", "D:\\chroma_embedding_models")

import chromadb
from src.config import CHROMA_PERSIST_DIR
from src.utils.logger import logger


class ChromaStore:
    """Chroma 向量数据库 —— 存储论文梗概的 embedding。"""

    def __init__(self, persist_dir: str = CHROMA_PERSIST_DIR):
        self.persist_dir = persist_dir
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(
            name="geo_papers",
            metadata={"hnsw:space": "cosine"},
        )

    def add_paper(self, digested) -> bool:
        """将一篇论文的中文梗概存入向量数据库。"""
        from src.models.paper import DigestedPaper
        p = digested.paper

        # 组合文本用于 embedding
        doc_text = (
            f"标题: {digested.chinese_title}\n"
            f"核心贡献: {digested.one_line_contribution}\n"
            f"方法论: {digested.methodology}\n"
            f"实验结果: {digested.experiment_results}\n"
            f"GEO启发: {digested.geo_insight}"
        )

        try:
            # 检查是否已存在
            existing = self.collection.get(ids=[p.arxiv_id])
            if existing and existing["ids"]:
                return False  # 已存在

            self.collection.add(
                ids=[p.arxiv_id],
                documents=[doc_text],
                metadatas=[{
                    "arxiv_id": p.arxiv_id,
                    "title": p.title,
                    "chinese_title": digested.chinese_title,
                    "published_date": p.published_date,
                    "relevance_score": p.relevance_score,
                    "pdf_url": p.pdf_url,
                }],
            )
            return True
        except Exception as e:
            logger.error(f"Chroma 写入失败 [{p.arxiv_id}]: {e}")
            return False

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """语义搜索论文。"""
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=top_k,
            )
            papers = []
            if results and results["ids"] and results["ids"][0]:
                for i, pid in enumerate(results["ids"][0]):
                    meta = results["metadatas"][0][i] if results["metadatas"] else {}
                    papers.append({
                        "arxiv_id": pid,
                        "title": meta.get("title", ""),
                        "chinese_title": meta.get("chinese_title", ""),
                        "published_date": meta.get("published_date", ""),
                        "relevance_score": meta.get("relevance_score", 0),
                        "pdf_url": meta.get("pdf_url", ""),
                        "snippet": results["documents"][0][i][:200] if results["documents"] else "",
                    })
            return papers
        except Exception as e:
            logger.error(f"Chroma 搜索失败: {e}")
            return []

    def count(self) -> int:
        """返回已索引的论文数。"""
        try:
            return self.collection.count()
        except Exception:
            return 0


# 全局单例
chroma_store = ChromaStore()
