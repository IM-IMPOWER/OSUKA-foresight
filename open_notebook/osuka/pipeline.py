import asyncio
import json
import re
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Callable, Tuple

from loguru import logger
from surreal_commands import execute_command_sync

from open_notebook.domain.notebook import Notebook, Note, Source, ChatSession
from open_notebook.database.repository import ensure_record_id
from commands.source_commands import SourceProcessingInput
from open_notebook.ai.models import DefaultModels, Model

from .competitors import load_competitors
from .discovery import discover_products


TABLE_MARKDOWN_PROMPT = """
Create a specs table in Markdown for all products across all brands in the sources.
Rules:
- Only include sources with a specific product and specs.
- Columns should include brand name, product name, and then attributes.
- Normalize similar attributes into the same column.
- Use "-" for missing values.
- Return ONLY the markdown table and nothing else.
""".strip()

# TABLE_MARKDOWN_PROMPT = """
# can you make a specs table of every product in your sources. have columns like brand, product names, followed by attributes. normalize similar specs and ignore sources without a product. Use "-" for missing values. limit each brand to no more than 5 products. Return ONLY the markdown table and nothing else.
# """.strip()

# TABLE_MARKDOWN_PROMPT = """
# can you make a full specs table of every product in your sources. have columns like brand, product names, followed by attributes. normalize similar specs and ignore sources without a product. Use "-" for missing values.
# """.strip()

# TABLE_MARKDOWN_PROMPT = """
# check all your sources carefully.
# make me a specs table of every product of every brand in your sources.
# look for words like specs, specifications, techincal data, product data,
# technical details or anything similar when reviewing your sources.
# have columns like brand, product names, followed by attributes.
# normalize similar specs.
# Use "-" for missing values.
# double check your sources so you don't miss any product or specs.
# include data for each product you found don't just give me the table column headers.
# """.strip()

#you may include brief notes, but include a Markdown table in your response.


TABLE_JSON_PROMPT = """
Convert the following Markdown table into STRICT JSON with this shape:
{
  "columns": ["brand", "product_name", "..."],
  "rows": [
    {"brand":"...", "product_name":"...", "...":"..."}
  ]
}
Return ONLY JSON, no extra text.
""".strip()

SHOPEE_BASE_URL = "https://osuka-shopee-scraper-354583366921.asia-southeast1.run.app"


async def _ensure_notebook(name: str, description: str) -> Notebook:
    notebook = Notebook(name=name, description=description)
    await notebook.save()
    return notebook


async def _add_source_link(notebook_id: str, url: str) -> Optional[Source]:
    source = Source(title=url, topics=[])
    await source.save()
    await source.add_to_notebook(notebook_id)

    command_input = SourceProcessingInput(
        source_id=str(source.id),
        content_state={"url": url},
        notebook_ids=[notebook_id],
        transformations=[],
        embed=False,
    )
    result = await asyncio.to_thread(
        execute_command_sync,
        "open_notebook",
        "process_source",
        command_input.model_dump(),
        timeout=300,
    )
    if not result.is_success():
        logger.warning(f"Source processing failed for {url}: {result.error_message}")
        return None
    processed = await Source.get(source.id)
    return processed


def _url_is_ok(url: str, timeout_s: int = 10) -> bool:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return 200 <= getattr(resp, "status", 0) < 400
    except Exception:
        return False


def _resolve_final_url(url: str, timeout_s: int = 10) -> str:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return getattr(resp, "url", "") or url
    except Exception:
        return url


async def _get_default_tools_model_name() -> Optional[str]:
    try:
        defaults = await DefaultModels.get_instance()
        model_id = defaults.default_tools_model or defaults.default_chat_model
        if not model_id:
            return None
        model = await Model.get(model_id)
        if getattr(model, "provider", "") != "google":
            return None
        return str(model.name or "").strip() or None
    except Exception as exc:
        logger.warning(f"DISCOVERY: failed to resolve default tools model ({exc})")
        return None


def _build_context_text(sources: List[Source], max_chars_per_source: int = 4000) -> str:
    parts = []
    for source in sources:
        title = source.title or "Untitled"
        text = source.full_text or ""
        if not text:
            continue
        trimmed = text[:max_chars_per_source]
        parts.append(f"Source: {title}\n{trimmed}")
    return "\n\n".join(parts)


async def _run_prompt(prompt: str, input_text: str) -> str:
    from open_notebook.graphs.prompt import graph as prompt_graph

    result = await prompt_graph.ainvoke(
        {
            "input_text": input_text,
            "prompt": prompt,
        }
    )
    return str(result.get("output", "")).strip()


async def _create_chat_session(notebook_id: str) -> ChatSession:
    session = ChatSession(title="Specs Table")
    await session.save()
    await session.relate_to_notebook(notebook_id)
    return session


def _seed_chat_messages(session_id: str, prompt: str, markdown_table: str) -> None:
    try:
        from langchain_core.messages import HumanMessage, AIMessage
        from langchain_core.runnables import RunnableConfig
        from open_notebook.graphs.chat import graph as chat_graph

        messages = [
            HumanMessage(content=prompt),
            AIMessage(content=markdown_table),
        ]
        config = RunnableConfig(configurable={"thread_id": session_id})
        if hasattr(chat_graph, "update_state"):
            chat_graph.update_state(config=config, values={"messages": messages})
            return
        logger.warning("Chat graph update_state not available; skipping chat seed")
    except Exception as exc:
        logger.warning(f"Failed to seed chat session: {exc}")


def _parse_price(value: str) -> Optional[float]:
    if not value:
        return None
    text = re.sub(r"[^0-9.,]", "", str(value))
    if not text:
        return None
    text = text.replace(",", "")
    try:
        return float(text)
    except Exception:
        return None


def _parse_sold(value: str) -> Optional[int]:
    if not value:
        return None
    text = str(value)
    idx = text.find("ขายแล้ว")
    if idx == -1:
        return None
    tail = text[idx:]
    match = re.search(r"ขายแล้ว\s*([0-9.,]+)\s*([kKmM]|พัน|หมื่น|แสน|ล้าน)?\+?", tail)
    if not match:
        return None
    number = match.group(1).replace(",", "")
    unit = (match.group(2) or "").lower()
    try:
        amount = float(number)
    except Exception:
        return None
    if unit == "k":
        amount *= 1000
    elif unit == "m":
        amount *= 1_000_000
    elif unit == "พัน":
        amount *= 1_000
    elif unit == "หมื่น":
        amount *= 10_000
    elif unit == "แสน":
        amount *= 100_000
    elif unit == "ล้าน":
        amount *= 1_000_000
    return int(amount)


async def _translate_category_to_thai(
    category: str,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> str:
    prompt = """
Translate the following product category into Thai.
Return ONLY the Thai text, no quotes, no extra text.
""".strip()
    try:
        if progress_cb:
            progress_cb("DISCOVERY: translating category to Thai for Shopee")
        translated = await _run_prompt(prompt, category)
        translated = translated.strip()
        return translated or category
    except Exception as exc:
        if progress_cb:
            progress_cb(f"DISCOVERY: Thai translation failed ({exc})")
    return category


def _fetch_shopee_results(category_th: str, timeout_s: int = 60) -> List[Dict[str, Any]]:
    keyword = urllib.parse.quote(category_th.strip())
    url = f"{SHOPEE_BASE_URL}/shopee_result/by_name/{keyword}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8")
    data = json.loads(raw)
    if not isinstance(data, list):
        return []
    items: List[Dict[str, Any]] = []
    for entry in data:
        result_raw = entry.get("result")
        try:
            result = json.loads(result_raw) if isinstance(result_raw, str) else result_raw
        except Exception:
            continue
        if isinstance(result, dict) and isinstance(result.get("data"), list):
            items.extend(result["data"])
    return items


async def run_osuka_pipeline(
    *,
    category: str,
    market: str,
    allow_external_brands: bool,
    max_total: int,
    max_shopee_products: int,
    competitor_path: str,
    preferred_brands: Optional[List[str]] = None,
    prefer_pdfs: bool = False,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    logs: List[str] = []

    def _log(message: str) -> None:
        logs.append(message)
        logger.info(message)
        if progress_cb:
            progress_cb(message)

    _log(f"DISCOVERY: start discovery for category={category}")
    competitors = load_competitors(competitor_path)
    _log(f"DISCOVERY: loaded {len(competitors)} competitors")
    market_label = market.strip() or "Global"
    model_name = await _get_default_tools_model_name()
    if model_name:
        _log(f"DISCOVERY: using tools model {model_name} for discovery")
    else:
        _log("DISCOVERY: using default discovery model")
    bangkok_tz = timezone(timedelta(hours=7))
    ts = datetime.now(bangkok_tz).strftime("%d/%m/%y %H:%M")
    notebook = await _ensure_notebook(
        name=f"{ts} {category}",
        description=f"Discovery for {category} ({market_label})",
    )
    _log(f"DISCOVERY: created notebook {notebook.id}")
    batch_size = 10
    min_text_len = 300
    max_loops = max(5, max_total * 3)
    seen_urls: set[str] = set()
    products: List[Dict[str, Any]] = []
    sources: List[Source] = []
    for loop_idx in range(1, max_loops + 1):
        if len(sources) >= max_total:
            break
        _log(f"DISCOVERY: discovery batch {loop_idx}/{max_loops} (target={max_total})")
        batch = discover_products(
            category=category,
            market=market_label,
            competitors=competitors,
            max_total=batch_size,
            allow_external_brands=allow_external_brands,
            preferred_brands=preferred_brands,
            prefer_pdfs=prefer_pdfs,
            model_name=model_name,
            progress_cb=_log,
            debug_dir=None,
        )
        _log(f"DISCOVERY: batch returned {len(batch)} items")
        for item in batch:
            if len(sources) >= max_total:
                break
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            final_url = _resolve_final_url(url)
            if final_url in seen_urls:
                continue
            seen_urls.add(final_url)
            if not _url_is_ok(final_url):
                _log(f"DISCOVERY: skipped (dead link) {url}")
                continue
            _log(f"DISCOVERY: adding source {final_url}")
            processed = await _add_source_link(str(notebook.id), final_url)
            if not processed:
                _log(f"DISCOVERY: source failed {url}")
                continue
            text_len = len(processed.full_text or "")
            if text_len < min_text_len:
                _log(f"DISCOVERY: skipped (short text={text_len}) {url}")
                continue
            sources.append(processed)
            products.append(item)
        _log(f"DISCOVERY: collected {len(sources)}/{max_total} sources")
    _log(f"DISCOVERY: discovery complete (products={len(products)})")

    _log(f"DISCOVERY: sources added {len(sources)}")
    context_text = _build_context_text(sources)
    _log("DISCOVERY: generating markdown table")
    markdown_table = await _run_prompt(TABLE_MARKDOWN_PROMPT, context_text)
    _log("DISCOVERY: generating JSON table")
    json_table = await _run_prompt(TABLE_JSON_PROMPT, markdown_table)

    table_note = Note(title="Specs Table (Markdown)", content=markdown_table, note_type="ai")
    await table_note.save()
    await table_note.add_to_notebook(str(notebook.id))

    json_note = Note(title="Specs Table (JSON)", content=json_table, note_type="ai")
    await json_note.save()
    await json_note.add_to_notebook(str(notebook.id))
    _log("DISCOVERY: notes saved")

    shopee_summary_note_id = None
    shopee_data_note_id = None
    shopee_count = 0
    category_th = await _translate_category_to_thai(category, progress_cb=_log)
    _log(f"DISCOVERY: Shopee keyword (TH) = {category_th}")
    try:
        sample_items = await asyncio.to_thread(_fetch_shopee_results, category_th)
    except Exception as exc:
        _log(f"DISCOVERY: Shopee fetch failed ({exc})")
        sample_items = []
    deduped: Dict[str, Dict[str, Any]] = {}
    for item in sample_items:
        key = str(item.get("link") or item.get("productId") or "").strip()
        if not key:
            continue
        if key in deduped:
            continue
        deduped[key] = item
    items = list(deduped.values())
    shopee_count = len(items)

    prices: List[Tuple[float, Dict[str, Any]]] = []
    sold_counts: List[Tuple[int, Dict[str, Any]]] = []
    gmv_total = 0.0
    for item in items:
        price_val = _parse_price(str(item.get("price") or ""))
        if price_val is not None:
            prices.append((price_val, item))
        sold_val = _parse_sold(str(item.get("sold") or "")) or 0
        sold_counts.append((sold_val, item))
        if price_val is not None and sold_val:
            gmv_total += price_val * sold_val

    avg_price = (
        sum(p for p, _ in prices) / len(prices) if prices else 0.0
    )
    total_sold = sum(s for s, _ in sold_counts) if sold_counts else 0
    max_price_item = max(prices, key=lambda x: x[0])[1] if prices else {}
    min_price_item = min(prices, key=lambda x: x[0])[1] if prices else {}
    most_sold_item = max(sold_counts, key=lambda x: x[0])[1] if sold_counts else {}

    def _sold_for_item(item: Dict[str, Any]) -> int:
        return _parse_sold(str(item.get("sold") or "")) or 0

    summary_lines = [
        f"Market size GMV (THB): {gmv_total:,.2f}",
        "",
        f"Unique items: {shopee_count}",
        f"Average price: {avg_price:.2f}" if prices else "Average price: N/A",
        f"Total items sold: {total_sold:,}" if total_sold else "Total items sold: N/A",
        "",
    ]
    if max_price_item:
        summary_lines.extend(
            [
                f"Max price item: {max_price_item.get('name','')}",
                f"Max price item price: {max_price_item.get('price','')}",
                f"Max price item units sold: {_sold_for_item(max_price_item):,}"
                if _sold_for_item(max_price_item)
                else "Max price item units sold: N/A",
                "",
            ]
        )
    if min_price_item:
        summary_lines.extend(
            [
                f"Min price item: {min_price_item.get('name','')}",
                f"Min price item price: {min_price_item.get('price','')}",
                f"Min price item units sold: {_sold_for_item(min_price_item):,}"
                if _sold_for_item(min_price_item)
                else "Min price item units sold: N/A",
                "",
            ]
        )
    if most_sold_item:
        summary_lines.extend(
            [
                f"Most sold item: {most_sold_item.get('name','')}",
                f"Most sold item price: {most_sold_item.get('price','')}",
                f"Most sold item units sold: {_sold_for_item(most_sold_item):,}"
                if _sold_for_item(most_sold_item)
                else "Most sold item units sold: N/A",
                "",
            ]
        )

    summary_text = "\n".join(summary_lines)
    summary_note = Note(
        title="Shopee Summary",
        content=summary_text,
        note_type="ai",
    )
    await summary_note.save()
    await summary_note.add_to_notebook(str(notebook.id))
    shopee_summary_note_id = str(summary_note.id)

    condensed = []
    for item in items:
        condensed.append(
            {
                "link": item.get("link", ""),
                "name": item.get("name", ""),
                "sold": _parse_sold(str(item.get("sold") or "")) or 0,
                "price": item.get("price", ""),
            }
        )
    data_note = Note(
        title="Shopee Products (JSON)",
        content=json.dumps(condensed, ensure_ascii=False, indent=2),
        note_type="ai",
    )
    await data_note.save()
    await data_note.add_to_notebook(str(notebook.id))
    shopee_data_note_id = str(data_note.id)
    _log(f"DISCOVERY: Shopee notes saved (items={shopee_count})")

    session = await _create_chat_session(str(notebook.id))
    _seed_chat_messages(str(session.id), TABLE_MARKDOWN_PROMPT, markdown_table)
    _log(f"DISCOVERY: chat session seeded {session.id}")

    return {
        "notebook_id": str(notebook.id),
        "sources_added": len(sources),
        "table_note_id": str(table_note.id),
        "json_note_id": str(json_note.id),
        "shopee_summary_note_id": shopee_summary_note_id,
        "shopee_data_note_id": shopee_data_note_id,
        "shopee_count": shopee_count,
        "chat_session_id": str(session.id),
        "products": products,
        "markdown_table": markdown_table,
        "logs": logs,
    }
