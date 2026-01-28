import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from google import genai

from .competitors import preferred_brand_list
from open_notebook.config import DATA_FOLDER


def _get_api_key() -> str:
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required for discovery.")
    return api_key


def _clean_json_text(raw_text: str) -> str:
    text = (raw_text or "").strip()
    if "```" in text:
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _parse_json_response(raw_text: str) -> Dict[str, Any]:
    cleaned = _clean_json_text(raw_text)
    # Strip control characters that break JSON parsing.
    cleaned = re.sub(r"[\x00-\x1F\x7F]", "", cleaned)
    if not cleaned:
        raise ValueError("Empty model response.")
    return json.loads(cleaned)


def _write_debug_file(debug_dir: Path, name: str, content: str) -> Optional[str]:
    try:
        debug_dir.mkdir(parents=True, exist_ok=True)
        path = debug_dir / name
        path.write_text(content or "", encoding="utf-8")
        return str(path)
    except Exception:
        return None


def _normalize_brand_key(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "", (text or "").lower())
    return value


def _infer_brand_key(
    title: str,
    snippet: str,
    url: str,
    competitors: List[Dict[str, Any]],
) -> str:
    haystack = " ".join([title or "", snippet or "", url or ""]).lower()
    for item in competitors:
        brand_key = str(item.get("brand_key", "")).strip()
        aliases = item.get("aliases") or []
        for alias in aliases:
            alias = str(alias or "").strip().lower()
            if alias and alias in haystack:
                return brand_key
    return ""


def translate_category_to_english(
    category: str,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> str:
    text = (category or "").strip()
    if not text:
        return ""
    client = genai.Client(api_key=_get_api_key())
    if progress_cb:
        progress_cb("Discovery: translating category to English")
    prompt = f"""
Translate the following product category to English.
Return ONLY the translated text with no extra words or punctuation.
Category: {text}
""".strip()
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={"temperature": 0.0},
    )
    translated = (getattr(response, "text", "") or "").strip()
    return translated


def discover_products(
    category: str,
    market: str,
    competitors: List[Dict[str, Any]],
    max_total: int = 10,
    allow_external_brands: bool = True,
    preferred_brands: Optional[List[str]] = None,
    category_en: Optional[str] = None,
    prefer_pdfs: bool = False,
    model_name: Optional[str] = None,
    progress_cb: Optional[Callable[[str], None]] = None,
    debug_dir: Optional[str] = None,
) -> List[Dict[str, Any]]:
    preferred = preferred_brands or preferred_brand_list(competitors)
    if progress_cb:
        progress_cb(f"Discovery: preferred brands = {', '.join(preferred) or 'none'}")
    category_en = (category_en or "").strip()
    category_line = f"Category: {category_en}" if category_en else f"Category: {category}"
    prompt = f"""
{category_line}
Market: {market}
Preferred brands: {", ".join(preferred)}
Max items: {max_total}

Task:
- Use Google Search grounding to find sources for this category.
- Prefer preferred brands but do not try to cover every brand.
- Prefer product catalogue/manual PDFs (with specs) over product pages.
- Product pages are allowed if needed, but PDFs should be prioritized.
- Exclude OSUKA products.
- Return no more than max_total items.
- ONLY output URLs that appear in grounded search results.
- Return exactly ONE JSON object. Do not output multiple JSON blocks.
- Do not include markdown fences, explanations, or extra text.

Output JSON ONLY:
{{
  "products": [
    {{
      "brand_key": "...",
      "url": "...",
      "title": "...",
      "snippet": "..."
    }}
  ]
}}
""".strip()
    if not prefer_pdfs:
        prompt = f"""
{category_line}
Market: {market}
Preferred brands: {", ".join(preferred)}
Max items: {max_total}

Task:
- Use Google Search grounding to find product pages for this category.
- Prefer preferred brands but do not try to cover every brand.
- Prefer individual product pages over category/listing pages.
- Manuals or product catalog PDFs are allowed if they contain specs for specific products.
- Exclude OSUKA products.
- Return no more than max_total items.
- ONLY output URLs that appear in grounded search results.
- Return exactly ONE JSON object. Do not output multiple JSON blocks.
- Do not include markdown fences, explanations, or extra text.

Output JSON ONLY:
{{
  "products": [
    {{
      "brand_key": "...",
      "url": "...",
      "title": "...",
      "snippet": "..."
    }}
  ]
}}
""".strip()

    client = genai.Client(api_key=_get_api_key())
    model_name = (model_name or "gemini-2.5-flash").strip()
    response = None
    raw_text = ""
    max_attempts = 5
    for attempt in range(max_attempts):
        if progress_cb:
            progress_cb(
                f"Discovery: model request start (attempt {attempt + 1}/{max_attempts})"
            )
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config={
                "temperature": 0.2,
                "tools": [{"google_search": {}}],
            },
        )
        if progress_cb:
            progress_cb("Discovery: model response received")
        raw_text = getattr(response, "text", "") or ""
        if raw_text.strip():
            break
        if progress_cb and attempt < max_attempts - 1:
            progress_cb("Discovery: empty response text, retrying")
    if progress_cb:
        progress_cb(f"Discovery: raw_text length={len(raw_text)}")
    debug_root = Path(debug_dir) if debug_dir else Path(DATA_FOLDER) / "osuka_debug"
    if not raw_text:
        try:
            response_dump = (
                response.model_dump()
                if hasattr(response, "model_dump")
                else {"repr": repr(response)}
            )
            dump_path = _write_debug_file(
                debug_root,
                f"discovery_response_{time.strftime('%Y%m%d_%H%M%S')}.json",
                json.dumps(response_dump, ensure_ascii=False, indent=2),
            )
            if progress_cb and dump_path:
                progress_cb(f"Discovery: raw response dump saved to {dump_path}")
        except Exception as exc:
            if progress_cb:
                progress_cb(f"Discovery: failed to dump response ({exc})")
    try:
        data = _parse_json_response(raw_text)
    except Exception as exc:
        raw_path = _write_debug_file(
            debug_root,
            f"discovery_raw_{time.strftime('%Y%m%d_%H%M%S')}.txt",
            raw_text,
        )
        if progress_cb and raw_path:
            progress_cb(f"Discovery: raw output saved to {raw_path}")
        if progress_cb:
            progress_cb("Discovery: parse failed, attempting JSON repair")
        repair_prompt = f"""
Fix the JSON to be valid and return ONLY the JSON object.
Do not add or remove products, only repair formatting.
{raw_text}
""".strip()
        repair_response = client.models.generate_content(
            model=model_name,
            contents=repair_prompt,
            config={"temperature": 0.0},
        )
        repair_text = getattr(repair_response, "text", "") or ""
        if progress_cb:
            progress_cb(f"Discovery: repair response length={len(repair_text)}")
        repaired_path = _write_debug_file(
            debug_root,
            f"discovery_repair_{time.strftime('%Y%m%d_%H%M%S')}.txt",
            repair_text,
        )
        if progress_cb and repaired_path:
            progress_cb(f"Discovery: repair output saved to {repaired_path}")
        data = _parse_json_response(repair_text)
    products = data.get("products", []) if isinstance(data, dict) else []
    if progress_cb:
        progress_cb(f"Discovery: model returned {len(products)} items")
    results: List[Dict[str, Any]] = []
    seen = set()
    for item in products:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        key = url.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        title = str(item.get("title") or "").strip()
        snippet = str(item.get("snippet") or "").strip()
        brand_key = str(item.get("brand_key") or "").strip()
        if not brand_key:
            brand_key = _infer_brand_key(title, snippet, url, competitors)
        if not brand_key and allow_external_brands:
            brand_key = _normalize_brand_key(title.split(" ")[0]) or "external"
        if "osuka" in brand_key.lower() or "osuka" in title.lower():
            continue
        results.append(
            {
                "brand_key": brand_key,
                "url": url,
                "title": title,
                "snippet": snippet,
            }
        )
        if len(results) >= max_total:
            break
    if progress_cb:
        progress_cb(f"Discovery: kept {len(results)} items after filtering")
    return results
