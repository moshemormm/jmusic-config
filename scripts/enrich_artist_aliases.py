import argparse
import json
import re
import shutil
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ARTISTS_FILE = ROOT / "allowed_artists.txt"
ARTIST_SOURCES_FILE = ROOT / "artist_sources.json"
CHANNEL_ID_RE = re.compile(r"(UC[0-9A-Za-z_-]{20,})")


def parse_allowed_artists() -> list[dict[str, str]]:
    if not ALLOWED_ARTISTS_FILE.exists():
        raise FileNotFoundError(f"Missing file: {ALLOWED_ARTISTS_FILE}")

    artists: list[dict[str, str]] = []
    for line_number, raw_line in enumerate(ALLOWED_ARTISTS_FILE.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue

        match = CHANNEL_ID_RE.search(line)
        if not match:
            print(f"Skipping line {line_number}: missing YouTube channel id")
            continue

        channel_id = match.group(1)
        name = line[: match.start()].strip(" \t|-:,") or channel_id
        artists.append({"name": name, "channelId": channel_id})

    unique: dict[str, dict[str, str]] = {}
    for artist in artists:
        unique[artist["channelId"]] = artist
    return list(unique.values())


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def normalize_alias(value: str | None) -> str:
    value = unicodedata.normalize("NFKC", value or "").strip()
    value = re.sub(r"\s+", " ", value)
    return value


def translate_name(name: str) -> str | None:
    try:
        from deep_translator import GoogleTranslator
    except Exception:
        print("deep-translator is not installed. Run: pip install -r requirements-aliases.txt")
        return None

    try:
        translated = GoogleTranslator(source="he", target="en").translate(name)
        translated = normalize_alias(translated)
        return translated or None
    except Exception as exc:
        print(f"Could not translate {name!r}: {exc}")
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich artist_sources.json with optional English aliases.")
    parser.add_argument("--use-google", action="store_true", help="Use deep-translator/GoogleTranslator to add English aliases.")
    parser.add_argument("--no-backup", action="store_true", help="Do not create a timestamped backup before saving.")
    args = parser.parse_args()

    artists = parse_allowed_artists()
    sources = load_json(ARTIST_SOURCES_FILE)

    if ARTIST_SOURCES_FILE.exists() and not args.no_backup:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup = ARTIST_SOURCES_FILE.with_suffix(f".backup_{stamp}.json")
        shutil.copy2(ARTIST_SOURCES_FILE, backup)
        print(f"Backup created: {backup}")

    for artist in artists:
        channel_id = artist["channelId"]
        name = artist["name"]

        entry = sources.get(channel_id)
        if not isinstance(entry, dict):
            entry = {}

        aliases = entry.get("aliases") or []
        if not isinstance(aliases, list):
            aliases = []

        normalized_aliases: list[str] = []
        for alias in [name, *aliases]:
            alias = normalize_alias(str(alias))
            if alias and alias not in normalized_aliases:
                normalized_aliases.append(alias)

        if args.use_google and re.search(r"[\u0590-\u05ff]", name):
            translated = translate_name(name)
            if translated and translated not in normalized_aliases:
                normalized_aliases.append(translated)

        entry["name"] = entry.get("name") or name
        entry["aliases"] = normalized_aliases
        entry["homeFeedEnabled"] = bool(entry.get("homeFeedEnabled", True))
        sources[channel_id] = entry

    ARTIST_SOURCES_FILE.write_text(json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Updated {ARTIST_SOURCES_FILE} with {len(artists)} artists.")
    print("Review aliases manually before committing if you used --use-google.")


if __name__ == "__main__":
    main()
