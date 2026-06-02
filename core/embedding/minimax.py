from typing import List, Optional
import requests

from .base import EmbeddingProvider


class MiniMaxEmbeddingProvider(EmbeddingProvider):
    """MiniMax Embedding provider（OpenAI 兼容接口）。

    MiniMax 的 embedding 响应结构与标准 OpenAI 略有差异，且批量支持
    有限，这里每次最多发送 16 条并做兼容处理。
    """

    MAX_BATCH_SIZE = 16

    def __init__(self, api_key: str, base_url: str, model_name: str, dimensions: Optional[int] = None):
        super().__init__("minimax", model_name, dimensions)
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        all_embeddings: List[List[float]] = []
        for i in range(0, len(texts), self.MAX_BATCH_SIZE):
            batch = texts[i : i + self.MAX_BATCH_SIZE]
            all_embeddings.extend(self._embed_batch(batch))
        return all_embeddings

    def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        payload = {"model": self.model_name, "input": texts}
        try:
            resp = requests.post(
                f"{self.base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
        except requests.exceptions.HTTPError as e:
            print(f"MiniMax Embedding API Error: {e}")
            print(f"Response body: {e.response.text}")
            raise

        result = resp.json()

        # 兼容多种响应格式
        data = result.get("data") or result.get("embeddings") or []
        if data and isinstance(data[0], dict):
            # OpenAI 标准格式: [{"embedding": [...], "index": N}]
            data_sorted = sorted(data, key=lambda x: x.get("index", 0))
            return [item["embedding"] for item in data_sorted]
        if data and isinstance(data[0], list):
            # 直接返回向量列表: [[...], [...]]
            return data

        # 如果批量失败，逐条降级
        print(f"MiniMax batch embedding returned unexpected format (keys={list(result.keys())}), falling back to single-text mode")
        return [self._embed_single(t) for t in texts]

    def _embed_single(self, text: str) -> List[float]:
        payload = {"model": self.model_name, "input": [text]}
        resp = requests.post(
            f"{self.base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        result = resp.json()

        data = result.get("data") or result.get("embeddings") or []
        if data and isinstance(data[0], dict):
            return data[0]["embedding"]
        if data and isinstance(data[0], list):
            return data[0]

        raise ValueError(f"MiniMax single embedding response unexpected: {list(result.keys())}")
