import json
import os
from typing import Any, Dict, List


def _default_competitor_path() -> str:
    return os.path.join(os.path.dirname(__file__), "competitor_pages.json")


def load_competitors(path: str | None = None) -> List[Dict[str, Any]]:
    path = path or _default_competitor_path()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and isinstance(data.get("competitors"), list):
        return data["competitors"]
    if isinstance(data, list):
        return data
    return []


def preferred_brand_list(competitors: List[Dict[str, Any]]) -> List[str]:
    names = []
    for item in competitors:
        name = str(item.get("display_name") or item.get("brand_key") or "").strip()
        if name and name not in names:
            names.append(name)
    return names

