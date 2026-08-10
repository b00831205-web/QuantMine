from __future__ import annotations

import json
import os
import re

from sqlalchemy.engine import Engine

from app.ai.chat import complete_chat
from app.api.v1.ai.db import get_config

def _provider_for(config: dict, model_id: str)->dict | None:
    for provider in config.get('providers', []):
        if model_id in provider.get('models',[]):
            return provider
    return None

def _call_llm(config: dict, *, system: str, prompt: str)-> str|None:
    model_id = config.get('defaultModel') or ''
    provider = _provider_for(config,model_id)
    api_key_env = (provider or {}).get('apiKeyEnv') or 'OPENAI_API_KEY'
    api_key = os.environ.get(api_key_env)
    if not model_id or not provider or not api_key:
        import sys
        print("[report-ai] model/key not configured, skipping AI analysis", file=sys.stderr)
        return None
    try:
        reply = complete_chat(
            system_prompt = system,
            history = [{'role': 'user', 'content': prompt}],
            model_id = model_id,
            temperature = config.get('temperature', 0.7),
            base_url = provider.get('baseUrl'),
            api_key = api_key,
            allow_query_database = False
        )
        return (reply.get('content') or '').strip() or None
    except Exception as exc:
        import sys
        print(f"[report-ai] LLM call failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return None

def _parse_ai_json(text: str)-> dict|None:
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.S)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            data = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None

def _parse_sections(text: str) -> dict[str, str]:
    data = _parse_ai_json(text)
    if not data:
        return {}
    sections = data.get('sections')
    if not isinstance(sections, list):
        return {}
    result: dict[str, str] = {}
    for item in sections:
        if not isinstance(item, dict):
            continue
        anchor = item.get('anchor')
        content = item.get('content')
        if isinstance(anchor, str) and isinstance(content, str) and content.strip():
            result[anchor] = content.strip()
    return result

def _appendix_text(context: dict) -> str:
    """Build appendix text from appendix_data; only sections with data are written, for the AI to read."""
    data = context.get("appendix_data") or {}
    lines = []

    yearly = data.get("yearly") or []
    if yearly:
        lines.append("A1 分年度 IC 表：")
        for r in yearly[:30]:
            lines.append(
                f"- {r['year']} {r['factor']} {r['period']}d "
                f"IC={r['ic_mean']} IR={r['ir']} n={r['n']}"
            )

    acf = data.get("acf") or []
    if acf:
        lines.append("A2 IC 自相关 ACF：")
        for r in acf[:40]:
            lines.append(
                f"- {r['factor']} {r['period']}d lag{r['lag']} ACF={r['acf']}"
            )

    alpha_beta = data.get("alpha_beta") or []
    if alpha_beta:
        lines.append("A5 回归 Alpha/Beta：")
        for r in alpha_beta:
            lines.append(f"- alpha={r['alpha']} beta={r['beta']} n={r['n']}")

    turnover = data.get("turnover") or []
    if turnover:
        lines.append("A6 换手率：")
        for r in turnover[:30]:
            lines.append(
                f"- {r['factor']} {r['period']}d rank{r['rank']} "
                f"turnover={r['turnover']}"
            )

    autocorr = data.get("factor_autocorr") or []
    if autocorr:
        lines.append("A6 因子自相关：")
        for r in autocorr:
            lines.append(f"- {r['factor']} autocorr={r['autocorr']}")

    sanity = data.get("sanity") or []
    if sanity:
        lines.append("A7 稳健性（位移/打乱）：")
        for r in sanity[:30]:
            lines.append(
                f"- {r['factor']} {r['period']}d {r['scenario']} "
                f"mean={r['mean_diff']} std={r['std_diff']}"
            )

    gross = data.get("gross") or []
    if gross:
        lines.append("A8 毛收益绩效：")
        for r in gross[:30]:
            lines.append(
                f"- {r['factor']} {r['period']}d rank{r['rank']} "
                f"total={r['total_return']} sharpe={r['sharpe']}"
            )
    return "\n".join(lines)


def _appendix_anchors(context: dict) -> list[str]:
    """Decide which appendix AI slots to fill based on whether appendix data exists."""
    data = context.get("appendix_data") or {}
    anchors = []
    if data.get("yearly"):
        anchors.append("a1")
    if data.get("acf"):
        anchors.append("a2")
    if data.get("ic_decay"):
        anchors.append("a4")
    if data.get("rolling_sharpe") or data.get("alpha_beta"):
        anchors.append("a5")
    if data.get("turnover") or data.get("factor_autocorr"):
        anchors.append("a6")
    if data.get("sanity"):
        anchors.append("a7")
    if data.get("gross"):
        anchors.append("a8")
    return anchors

def build_report_text(context: dict, lang: str) -> tuple[str, list[str]]:
    """Build the report text version the AI will see, plus the anchor list that still needs analysis."""
    ai_slots = context.get("ai") or {}
    anchors = [key for key, value in ai_slots.items() if value is None]

    meta = context.get("meta") or {}
    lines = [
        "# 量化研究报告",
        f"- Run: {meta.get('run_id')}  Test: {meta.get('test_id')}  Git: {meta.get('git_commit')}",
        f"- 生成时间: {meta.get('generated_at')}",
        "",
    ]

    # 1. IC 检验表
    lines.append("## 1. IC 检验")
    lines.append("| variant | factor | period | IC | IR | t | p | 显著 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in (context.get("ic_rows") or [])[:40]:
        lines.append(
            f"| {r.get('variant')} | {r.get('factor')} | {r.get('period')} | "
            f"{r.get('ic_mean')} | {r.get('ir')} | {r.get('t')} | {r.get('p')} | {r.get('bonf')} |"
        )
    lines.append("")

    # 2. 回测分组表
    lines.append("## 2. 回测分组")
    for group in (context.get("backtest_groups") or [])[:10]:
        lines.append(f"### {group.get('label')}")
        lines.append("| 组 | 年化 | 波动 | 夏普 | 回撤 | 胜率 |")
        lines.append("|---|---|---|---|---|---|")
        for r in (group.get("rows") or [])[:8]:
            lines.append(
                f"| {r.get('group')} | {r.get('ann')} | {r.get('vol')} | "
                f"{r.get('sharpe')} | {r.get('mdd')} | {r.get('win')} |"
            )
        mono = group.get("mono") or {}
        if mono:
            lines.append(
                f"单调性: corr={mono.get('corr')} p={mono.get('p')} "
                f"日频正占比={mono.get('pos')}"
            )
        lines.append("")

    # 3. 总结
    lines.append("## 3. 总结")
    for item in context.get("summary_rows") or []:
        lines.append(f"- {item.get('dim')} / {item.get('metric')}: {item.get('value')}")
    lines.append("")

    # 附录
    lines.append("## 附录")
    for item in context.get("appendix_items") or []:
        lines.append(f"- {item.get('code')} {item.get('title')}: {item.get('note')}")
    appendix_text = _appendix_text(context)
    if appendix_text:
        lines.append("")
        lines.append(appendix_text)
    anchors = [
        key for key, value in (context.get("ai") or {}).items()
        if value is None
    ]
    for anchor in _appendix_anchors(context):
        if anchor not in anchors:
            anchors.append(anchor)
    return "\n".join(lines), anchors

def generate_report_analysis(
        engine: Engine,
        *,
        context: dict,
        lang: str,
) -> dict:
    config = get_config(engine)
    ai = dict(context.get('ai') or {})
    for anchor in _appendix_anchors(context):
        ai.setdefault(anchor, None)
    report_text, anchors = build_report_text(context, lang)
    if not anchors:
        return ai

    language = "中文" if lang == "zh" else "English"
    role = config.get("systemPrompt") or "你是一名量化研究分析师。"
    system = (
        f"{role}\n"
        f"请用{language}撰写，专业、简洁、基于数据，避免空泛套话。"
    )

    prompt = (
        "以下是即将生成的量化研究报告的文本内容"
        "（图表为图片已省略，表格是报告中的实际数据）：\n\n"
        f"{report_text}\n\n"
        f"请为以下章节撰写 AI 解读：{', '.join(anchors)}\n"
        "要求：\n"
        "- 每段 100~150 字；\n"
        "- 只返回一个 JSON 对象，不要输出其他任何文字；\n"
        '- 格式：{"sections": [{"anchor": "ic", "content": "..."}, {"anchor": "backtest", "content": "..."}]}\n'
        "- anchor 只能使用上面给出的章节名。"
    )

    text = _call_llm(config, system = system, prompt = prompt)
    if text:
        sections = _parse_sections(text)
        for anchor, content in sections.items():
            if anchor in ai and content:
                ai[anchor] = content
        if not any(ai.values()):
            ai['overall'] = text
    return ai