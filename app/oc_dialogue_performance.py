"""Dialogue Performance Agent — v0.9

Splits dialogue into performance units: splits sentences, tags each with
intent/emotion/pause/emphasis/distance, and separates clean text from control
layer. TTS only reads clean text; control info is passed independently.
"""

from __future__ import annotations

from .llm_client import chat_json
from .oc_models import OCDraft

PERFORMANCE_PROMPT = """你是 Dialogue Performance Agent（对话表演导演）。将一段台词拆分为可逐句表演的单元。

## 输出格式：
{
  "units": [
    {
      "index": 0,
      "clean_text": "去掉所有控制标记后的干净台词，直接用于 TTS",
      "intent": "这句的意图（问候/拒绝/解释/讽刺/沉默/回避）",
      "emotion": "情绪（calm/sad/cold/tired/angry/gentle）",
      "pause_before_ms": 0,
      "pause_after_ms": 0,
      "emphasis_words": ["需要重读的词"],
      "distance": "与听众的距离感（distant/intimate/casual/formal）",
      "volume": "音量相对变化（normal/soft/loud/whisper）",
      "speed": "语速（normal/slow/fast）",
      "notes": "表演备注"
    }
  ],
  "overall_tone": "整体语气描述",
  "performance_summary": "一句表演总纲"
}

规则：
- clean_text 必须是纯台词，不含任何 [tag] 或 () 标记
- 每句独立标注，不做句子合并
- 停顿根据标点和语义判断
- 情绗从角色性格和当前语境推断"""


async def analyze_performance(text: str, draft: OCDraft | None = None) -> dict:
    """Analyze dialogue text and produce performance units."""
    context = ""
    if draft:
        if draft.name:
            context += f"角色: {draft.name}\n"
        if draft.personality:
            context += f"性格: {', '.join(draft.personality)}\n"
        if draft.speaking_style:
            context += f"说话方式: {draft.speaking_style}\n"

    prompt = f"{context}\n台词:\n{text}\n\n请分析表演方案。"

    try:
        result = await chat_json(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=PERFORMANCE_PROMPT,
            agent="designer",
        )
        return result
    except Exception:
        # Fallback: single unit
        return {
            "units": [{"index": 0, "clean_text": text, "intent": "statement", "emotion": "calm",
                        "pause_before_ms": 0, "pause_after_ms": 0, "emphasis_words": [],
                        "distance": "casual", "volume": "normal", "speed": "normal", "notes": ""}],
            "overall_tone": "",
            "performance_summary": "",
        }
