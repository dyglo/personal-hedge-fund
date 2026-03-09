from __future__ import annotations

import json
from typing import Any

from tavily import TavilyClient

from hedge_fund.domain.exceptions import ProviderError


class TavilySearchClient:
    def __init__(self, api_key: str | None, max_results: int, search_depth: str) -> None:
        self.api_key = api_key
        self.max_results = max_results
        self.search_depth = search_depth
        self._client = TavilyClient(api_key=api_key) if api_key else None

    def search(self, query: str) -> dict[str, Any]:
        payload = self.raw_search(query)
        results = []
        for item in payload.get("results", [])[: self.max_results]:
            results.append(
                {
                    "title": item.get("title", "").strip(),
                    "url": item.get("url", "").strip(),
                    "snippet": (item.get("content") or item.get("raw_content") or "").strip(),
                }
            )

        summary = self._summarize(payload.get("answer"), results)
        return {
            "query": query,
            "summary": summary,
            "results": results,
        }

    def raw_search(self, query: str) -> dict[str, Any]:
        if not self._client:
            raise ProviderError("Missing TAVILY_API_KEY")
        try:
            payload = self._client.search(
                query=query,
                max_results=self.max_results,
                search_depth=self.search_depth,
            )
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"Tavily search failed: {exc.__class__.__name__}") from exc
        if isinstance(payload, str):
            try:
                return json.loads(payload)
            except ValueError:
                return {"answer": payload, "results": []}
        return payload

    def _summarize(self, answer: str | None, results: list[dict[str, str]]) -> str:
        if answer and answer.strip():
            return answer.strip()
        if not results:
            return "No relevant live search results were returned."

        snippets = []
        for item in results[:3]:
            title = item["title"] or "Untitled source"
            snippet = item["snippet"] or "No summary available."
            snippets.append(f"{title}: {snippet}")
        return " ".join(snippets)
