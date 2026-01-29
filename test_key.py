
import os
from pathlib import Path

import google.generativeai as genai


def _load_env_key() -> str | None:
    key = os.getenv("GOOGLE_API_KEY")
    if key:
        return key.strip()
    env_path = Path(".env")
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == "GOOGLE_API_KEY":
            return value.strip().strip('"').strip("'")
    return None


def main() -> None:
    api_key = _load_env_key()
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY not found in env or .env")

    genai.configure(api_key=api_key)

    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content("Say 'OK' if you can read this.")

    print("Request succeeded.")
    print("Response:")
    print(response.text)


if __name__ == "__main__":
    main()
