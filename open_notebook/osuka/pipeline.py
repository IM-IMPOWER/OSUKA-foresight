import asyncio
import urllib.request
from typing import Any, Dict, List, Optional, Callable

from loguru import logger
from surreal_commands import execute_command_sync

from open_notebook.domain.notebook import Notebook, Note, Source, ChatSession
from open_notebook.database.repository import ensure_record_id
from commands.source_commands import SourceProcessingInput

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


async def run_osuka_pipeline(
    *,
    category: str,
    market: str,
    allow_external_brands: bool,
    max_total: int,
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

    _log(f"OSUKA: start discovery for category={category}")
    competitors = load_competitors(competitor_path)
    _log(f"OSUKA: loaded {len(competitors)} competitors")
    market_label = market.strip() or "Global"
    notebook = await _ensure_notebook(
        name=f"OSUKA {category}",
        description=f"OSUKA discovery for {category} ({market_label})",
    )
    _log(f"OSUKA: created notebook {notebook.id}")
    batch_size = 3
    min_text_len = 300
    max_loops = max(5, max_total * 3)
    seen_urls: set[str] = set()
    products: List[Dict[str, Any]] = []
    sources: List[Source] = []
    for loop_idx in range(1, max_loops + 1):
        if len(sources) >= max_total:
            break
        _log(f"OSUKA: discovery batch {loop_idx}/{max_loops} (target={max_total})")
        batch = discover_products(
            category=category,
            market=market_label,
            competitors=competitors,
            max_total=batch_size,
            allow_external_brands=allow_external_brands,
            preferred_brands=preferred_brands,
            prefer_pdfs=prefer_pdfs,
            progress_cb=_log,
            debug_dir=None,
        )
        _log(f"OSUKA: batch returned {len(batch)} items")
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
                _log(f"OSUKA: skipped (dead link) {url}")
                continue
            _log(f"OSUKA: adding source {final_url}")
            processed = await _add_source_link(str(notebook.id), final_url)
            if not processed:
                _log(f"OSUKA: source failed {url}")
                continue
            text_len = len(processed.full_text or "")
            if text_len < min_text_len:
                _log(f"OSUKA: skipped (short text={text_len}) {url}")
                continue
            sources.append(processed)
            products.append(item)
        _log(f"OSUKA: collected {len(sources)}/{max_total} sources")
    _log(f"OSUKA: discovery complete (products={len(products)})")

    _log(f"OSUKA: sources added {len(sources)}")
    context_text = _build_context_text(sources)
    _log("OSUKA: generating markdown table")
    markdown_table = await _run_prompt(TABLE_MARKDOWN_PROMPT, context_text)
    _log("OSUKA: generating JSON table")
    json_table = await _run_prompt(TABLE_JSON_PROMPT, markdown_table)

    table_note = Note(title="Specs Table (Markdown)", content=markdown_table, note_type="ai")
    await table_note.save()
    await table_note.add_to_notebook(str(notebook.id))

    json_note = Note(title="Specs Table (JSON)", content=json_table, note_type="ai")
    await json_note.save()
    await json_note.add_to_notebook(str(notebook.id))
    _log("OSUKA: notes saved")

    session = await _create_chat_session(str(notebook.id))
    _seed_chat_messages(str(session.id), TABLE_MARKDOWN_PROMPT, markdown_table)
    _log(f"OSUKA: chat session seeded {session.id}")

    return {
        "notebook_id": str(notebook.id),
        "sources_added": len(sources),
        "table_note_id": str(table_note.id),
        "json_note_id": str(json_note.id),
        "chat_session_id": str(session.id),
        "products": products,
        "markdown_table": markdown_table,
        "logs": logs,
    }
