import json
from pathlib import Path

import requests

url = "https://www.searchapi.io/api/v1/search"
params = {
  "engine": "youtube_transcripts",
  "video_id": "t8jTh9SrzZg",
  "api_key": "mvYBWSgcWW395X2KEUGKJQVP",
  "lang": "th",
  "only_available":"true"
}

response = requests.get(url, params=params)
print(response.text)

out_path = Path("data/search_api_response.json")
out_path.parent.mkdir(parents=True, exist_ok=True)
try:
    out_path.write_text(json.dumps(response.json(), ensure_ascii=False, indent=2), encoding="utf-8")
except Exception:
    out_path.write_text(response.text, encoding="utf-8")
