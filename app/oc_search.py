"""Search Agent — v0.4 full implementation.

Handles: trigger detection, query building, web search (DuckDuckGo),
result filtering, inspiration synthesis, and persistence.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from . import db
from .config import get_config
from .llm_client import chat, chat_json
from .oc_models import (
    InspirationCard,
    OCDraft,
    SearchQueryPlan,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from .search_providers import list_providers, resolve_provider

# ─── Keywords for fast trigger check ──────────────────

TRIGGER_KEYWORDS = {
    "mythology": [
        "神", "神明", "宗教", "祭司", "圣女", "天使", "恶魔", "诅咒", "仪式",
        "信仰", "教会", "神殿", "祭祀", "祈祷", "神谕", "显灵",
    ],
    "history": [
        "中世纪", "维多利亚", "拜占庭", "古罗马", "唐朝", "战国", "昭和",
        "民俗", "传说", "朝代", "古代", "近代",
    ],
    "profession": [
        "骑士", "修女", "杀手", "医生", "法官", "军官", "侦探", "炼金术师",
        "巫女", "贵族", "士兵", "佣兵", "法师", "剑客",
    ],
    "style": [
        "哥特", "赛博朋克", "蒸汽朋克", "废土", "都市奇幻", "黑暗童话",
        "克苏鲁", "怪谈", "和风", "西幻", "国风",
    ],
    "weapon_costume": [
        "长枪", "镰刀", "弓", "火枪", "仪式剑", "军装", "礼服", "修女服",
        "盔甲", "制服", "铠甲", "长袍", "披风",
    ],
    "scifi": [
        "义体", "仿生人", "殖民星", "实验体", "AI", "记忆芯片", "机甲",
        "赛博", "人工智能", "基因", "克隆",
    ],
    "action": [
        "搜索", "查一下", "搜一下", "帮我搜", "查查", "找找", "参考",
        "资料", "素材", "灵感",
    ],
}

TRIGGER_PROMPT = """判断以下用户消息是否涉及需要联网搜索的领域知识。
如果用户提到了具体职业、历史时期、文化背景、技术概念、神话体系、地域、
服饰、武器等需要背景知识的内容，返回 true。否则返回 false。

返回 JSON:
{"should_search": true/false, "reason": "...", "category": "...", "queries": ["词1", "词2"]}"""

QUERY_PROMPT = """你是搜索查询生成器。根据角色创作上下文，生成 2-3 个英文搜索关键词。

规则：
- 查询词必须是具体可搜索的关键词短语，不要用问句
- 优先搜索用户提到的具体文化/历史/职业概念
- 结合角色当前设定生成相关查询
- 每个查询词不超过 8 个单词

输出 JSON: {"queries": ["query1", "query2", "query3"]}"""

SYNTHESIS_PROMPT = """你是创作灵感合成师。根据搜索结果和角色设定，生成可直接用于角色完善的创作建议。

## 输出格式（严格 JSON）：
{
  "title": "灵感方向标题",
  "summary": "1句话概括这个方向",
  "usable_ideas": ["具体可执行的设定建议1", "建议2", "建议3"],
  "cautions": ["注意事项"],
  "related_fields": ["background", "appearance", "abilities"]
}

规则：
- usable_ideas 每条必须是一个具体的、可执行的设定建议，AI 可以直接据此完善角色
- 例如不要写"参考日本战国文化"，要写"加入家纹设定，她的衣服上暗藏某个已灭亡家族的纹章"
- 每条建议要和当前角色设定有明确关联
- 3-5 条"""


# ─── Trigger detection ─────────────────────────────────

def _check_keywords(text: str) -> SearchQueryPlan | None:
    """Fast keyword-based trigger check."""
    text_lower = text.lower()
    matched_queries: list[str] = []
    for _category, words in TRIGGER_KEYWORDS.items():
        for w in words:
            if w in text_lower or w in text:
                matched_queries.append(w)
    if matched_queries:
        return SearchQueryPlan(
            should_search=True,
            reason=f"关键词匹配: {', '.join(matched_queries[:5])}",
            category="keyword_match",
            queries=matched_queries[:3],
        )
    return None


async def search_trigger(user_message: str, draft: OCDraft) -> SearchQueryPlan:
    """Decide whether a search is warranted. Keyword first, then LLM."""
    plan = _check_keywords(user_message)
    if plan and plan.should_search:
        return plan

    context = ""
    if draft and draft.core_concept:
        context = f"角色: {draft.core_concept}\n"
        if draft.themes:
            context += f"主题: {', '.join(draft.themes)}\n"

    try:
        result = await chat_json(
            messages=[{"role": "user", "content": f"{context}\n用户消息: {user_message}"}],
            system_prompt=TRIGGER_PROMPT,
            agent="designer",
        )
        return SearchQueryPlan(
            should_search=result.get("should_search", False),
            reason=result.get("reason"),
            category=result.get("category"),
            queries=result.get("queries", [])[:3],
        )
    except Exception as e:
        return SearchQueryPlan(should_search=False, reason=f"LLM trigger failed: {e}")


# ─── Query builder ─────────────────────────────────────

async def build_queries(user_message: str, draft: OCDraft) -> list[str]:
    """Generate search queries from context. Falls back to keywords."""
    context = ""
    if draft and draft.core_concept:
        context = f"角色设定: {draft.core_concept}\n"
    elif draft and hasattr(draft, 'core_concept'):
        context = ""

    prompt = f"{context}用户创作想法: {user_message}\n\n生成 2-3 个英文搜索关键词。"

    try:
        result = await chat_json(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=QUERY_PROMPT,
            agent="designer",
        )
        return result.get("queries", [])[:3]
    except Exception:
        return _fallback_queries(user_message)


def _fallback_queries(text: str) -> list[str]:
    """Extract meaningful keywords when LLM fails."""
    queries = []
    for _cat, words in TRIGGER_KEYWORDS.items():
        for w in words:
            if w in text and w not in queries and len(w) > 1:
                queries.append(w)
    return queries[:3] if queries else [text[:30]]


# ─── Web search ────────────────────────────────────────

def _is_search_available() -> bool:
    """Return True if at least one search provider is available."""
    return any(p["available"] for p in list_providers())


async def search_web(queries: list[str]) -> list[SearchResult]:
    """Execute searches for each query using the best available provider."""
    cfg = get_config()
    sc = cfg.get("search", {})
    provider = resolve_provider(sc)
    rpq = sc.get("results_per_query", 3)

    all_results: list[SearchResult] = []
    for q in queries[: sc.get("max_queries", 3)]:
        batch = await provider.search(q, max_results=rpq)
        all_results.extend(batch)
    return all_results


# ─── Filter ─────────────────────────────────────────────

def filter_results(results: list[SearchResult]) -> list[SearchResult]:
    """Deduplicate and quality-filter results."""
    cfg = get_config()
    max_r = cfg.get("search", {}).get("max_results", 6)

    seen_urls: set[str] = set()
    filtered: list[SearchResult] = []

    for r in results:
        if r.url in seen_urls:
            continue
        if not r.title or r.title == "(no title)":
            continue
        if len(r.snippet) < 20:
            continue
        seen_urls.add(r.url)
        r.score = min(len(r.snippet) / 500.0, 1.0)
        filtered.append(r)

    filtered.sort(key=lambda x: x.score, reverse=True)
    return filtered[:max_r]


# ─── Synthesis ─────────────────────────────────────────

async def synthesize_inspiration(
    user_message: str,
    draft: OCDraft,
    results: list[SearchResult],
) -> InspirationCard:
    """Turn search results into a creative inspiration card."""
    if not results:
        return InspirationCard(
            title="无搜索结果",
            summary="未找到相关素材，可以尝试换个方向搜索。",
        )

    context = ""
    if draft and draft.core_concept:
        context = f"角色: {draft.core_concept}\n"

    snippets = "\n".join(
        f"[{r.title}] {r.snippet[:200]}" for r in results[:4]
    )

    prompt = f"""{context}
用户正在创作的灵感: {user_message}

搜索到的参考资料:
{snippets}

请根据以上资料生成创作灵感卡。"""

    try:
        raw = await chat_json(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=SYNTHESIS_PROMPT,
            agent="designer",
        )
        return InspirationCard(
            title=raw.get("title", "搜索灵感"),
            summary=raw.get("summary", ""),
            usable_ideas=raw.get("usable_ideas", []),
            cautions=raw.get("cautions", []),
            related_fields=raw.get("related_fields", []),
            sources=results[:4],
        )
    except Exception:
        return InspirationCard(
            title="搜索结果",
            summary="以下是根据搜索整理的参考资料：",
            usable_ideas=[f"{r.title}: {r.snippet[:120]}" for r in results[:4]],
            sources=results[:4],
        )


# ─── Main pipeline ─────────────────────────────────────

async def search_and_inspire(
    session_id: str,
    user_message: str,
    draft: OCDraft,
    mode: str = "manual",
) -> SearchResponse:
    """Run the full search pipeline and persist results."""
    cfg = get_config()
    enabled = cfg.get("features", {}).get("search_enabled", False)

    if not enabled:
        return SearchResponse(ok=False, error="搜索功能未启用，请在 config.yaml 中开启 features.search_enabled")

    if not user_message.strip():
        return SearchResponse(ok=False, error="搜索内容不能为空")

    if not _is_search_available():
        return SearchResponse(ok=False, error="没有可用的搜索后端。请配置 SERPER_API_KEY / TAVILY_API_KEY / SearXNG，或安装 ddgs: pip install ddgs")

    # 1. Build queries
    queries = await build_queries(user_message, draft)
    if not queries:
        return SearchResponse(ok=False, error="无法生成搜索关键词，请尝试更具体的描述")

    # 2. Search
    results = await search_web(queries)
    if not results:
        return SearchResponse(ok=False, error="未找到搜索结果，请换个方向试试")

    # 3. Filter
    filtered = filter_results(results)
    if not filtered:
        return SearchResponse(ok=False, error="搜索结果过滤后无有效内容")

    # 4. Synthesize
    inspiration = await synthesize_inspiration(user_message, draft, filtered)

    # 5. Persist
    try:
        db.insert_search_run(
            session_id,
            json.dumps({"query": user_message, "mode": mode, "queries": queries}),
            json.dumps([r.model_dump() for r in filtered]),
            inspiration.model_dump_json(),
        )
    except Exception:
        pass  # persistence failure is non-fatal

    return SearchResponse(ok=True, inspiration=inspiration, results=filtered)
