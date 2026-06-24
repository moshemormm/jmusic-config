import json
import os
import re
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from ytmusicapi import YTMusic

try:
    from rapidfuzz import fuzz
    RAPIDFUZZ_AVAILABLE = True
except Exception:  # pragma: no cover - dependency is installed in GitHub Actions via requirements.txt
    fuzz = None
    RAPIDFUZZ_AVAILABLE = False


ROOT = Path(__file__).resolve().parents[1]

ALLOWED_ARTISTS_FILE = ROOT / "allowed_artists.txt"
ARTIST_SOURCES_FILE = ROOT / "artist_sources.json"

OUTPUT_FILE = ROOT / "home_feed.json"
REPORT_FILE = ROOT / "home_feed_report.json"

CACHE_DIR = ROOT / "cache"
ITUNES_LOOKUP_CACHE_FILE = CACHE_DIR / "itunes_lookup_cache.json"
YOUTUBE_ALBUM_CACHE_FILE = CACHE_DIR / "youtube_album_details_cache.json"

ITUNES_COUNTRY = os.getenv("ITUNES_COUNTRY", "IL").strip().upper()

MAX_ITEMS_PER_ARTIST_CATEGORY = int(os.getenv("MAX_ITEMS_PER_ARTIST_CATEGORY", "8"))
ARTIST_ALBUMS_LIMIT = int(os.getenv("ARTIST_ALBUMS_LIMIT", "80"))

MAX_POPULAR_ARTISTS = int(os.getenv("MAX_POPULAR_ARTISTS", "20"))
MAX_POPULAR_SONGS = int(os.getenv("MAX_POPULAR_SONGS", "20"))
POPULAR_SONGS_PER_ARTIST = int(os.getenv("POPULAR_SONGS_PER_ARTIST", "5"))

YOUTUBE_REQUEST_DELAY_SECONDS = float(os.getenv("YOUTUBE_REQUEST_DELAY_SECONDS", "0.7"))

ITUNES_REQUEST_DELAY_SECONDS = float(os.getenv("ITUNES_REQUEST_DELAY_SECONDS", "4.0"))
ITUNES_429_SLEEP_SECONDS = int(os.getenv("ITUNES_429_SLEEP_SECONDS", "90"))
ITUNES_MAX_RETRIES = int(os.getenv("ITUNES_MAX_RETRIES", "2"))

MAX_ITUNES_LOOKUPS_TOTAL = int(os.getenv("MAX_ITUNES_LOOKUPS_TOTAL", "150"))

MAX_RELEASE_AGE_DAYS = int(os.getenv("MAX_RELEASE_AGE_DAYS", "180"))
MIN_RELEASE_DATE = os.getenv("MIN_RELEASE_DATE", "").strip()

ENABLE_NAME_MATCH = os.getenv("ENABLE_NAME_MATCH", "true").strip().lower() == "true"
MIN_MATCH_SCORE = int(os.getenv("MIN_MATCH_SCORE", "78"))
MIN_ARTIST_MATCH_SCORE = int(os.getenv("MIN_ARTIST_MATCH_SCORE", "28"))
MIN_TITLE_MATCH_SCORE = int(os.getenv("MIN_TITLE_MATCH_SCORE", "30"))
ENABLE_RAPIDFUZZ = os.getenv("ENABLE_RAPIDFUZZ", "true").strip().lower() == "true"

ENABLE_HEBREW_TRANSLITERATION = os.getenv("ENABLE_HEBREW_TRANSLITERATION", "true").strip().lower() == "true"
MAX_AUTO_ALIASES_PER_ARTIST = int(os.getenv("MAX_AUTO_ALIASES_PER_ARTIST", "8"))
MAX_SEARCH_ALIASES_PER_ITEM = int(os.getenv("MAX_SEARCH_ALIASES_PER_ITEM", "6"))

ENABLE_YOUTUBE_DRILLDOWN_FOR_VIDEO_ID = os.getenv(
    "ENABLE_YOUTUBE_DRILLDOWN_FOR_VIDEO_ID",
    "true",
).strip().lower() == "true"

REFRESH_ITUNES_CACHE = os.getenv("REFRESH_ITUNES_CACHE", "false").strip().lower() == "true"
REFRESH_YOUTUBE_CACHE = os.getenv("REFRESH_YOUTUBE_CACHE", "false").strip().lower() == "true"

CHANNEL_ID_RE = re.compile(r"(UC[0-9A-Za-z_-]{20,})")


HEBREW_NAME_ALIASES = {
    "קובי": ["kobi", "koby", "cobi", "coby"],
    "משה": ["moshe"],
    "מושי": ["moshi", "moishy", "moyshe"],
    "שמוליק": ["shmueli", "shmulik", "shmuelik"],
    "שמואל": ["shmuel", "samuel"],
    "יעקב": ["yaakov", "yakov", "jacob"],
    "חיים": ["chaim", "haim"],
    "יצחק": ["yitzchak", "itzhak", "itzik", "isaac"],
    "אברהם": ["avraham", "abraham"],
    "אברומי": ["avrumi", "avromi", "abrumi"],
    "יוסף": ["yosef", "yossi", "joseph"],
    "יוסי": ["yossi", "yosef"],
    "דוד": ["david", "dovid"],
    "דודי": ["dudi", "dudy", "dovid"],
    "אלי": ["eli"],
    "אליהו": ["eliyahu", "eli"],
    "מוטי": ["moti", "mutty", "motty"],
    "מרדכי": ["mordechai", "mordechay", "mordy"],
    "בערי": ["beri", "berry", "bere"],
    "שלמה": ["shlomo", "shloime", "solomon"],
    "ישראל": ["yisrael", "israel"],
    "אהרן": ["aharon", "aaron"],
    "ארי": ["ari"],
    "יהודה": ["yehuda", "judah"],
    "נתן": ["natan", "nosson", "nathan"],
    "נפתלי": ["naftali", "naftuly"],
    "אבי": ["avi", "avy"],
    "אבישי": ["avishai"],
    "ישי": ["ishay", "yishai"],
    "עקיבא": ["akiva", "akiba"],
    "אלעזר": ["elazar", "eliezer"],
    "מאיר": ["meir", "meyer"],
    "מיכאל": ["michael"],
}

HEBREW_LETTER_ALIASES = {
    "א": [""],
    "ב": ["b", "v"],
    "ג": ["g"],
    "ד": ["d"],
    "ה": ["h", ""],
    "ו": ["o", "u", "v", "w"],
    "ז": ["z"],
    "ח": ["ch", "h"],
    "ט": ["t"],
    "י": ["i", "y"],
    "כ": ["ch", "k", "kh"],
    "ך": ["ch", "k", "kh"],
    "ל": ["l"],
    "מ": ["m"],
    "ם": ["m"],
    "נ": ["n"],
    "ן": ["n"],
    "ס": ["s"],
    "ע": ["", "a"],
    "פ": ["p", "f"],
    "ף": ["f"],
    "צ": ["tz", "z"],
    "ץ": ["tz", "z"],
    "ק": ["k", "c"],
    "ר": ["r"],
    "ש": ["sh", "s"],
    "ת": ["t", "s"],
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_utc() -> date:
    return datetime.now(timezone.utc).date()


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None

    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def cutoff_date() -> date:
    explicit = parse_iso_date(MIN_RELEASE_DATE)
    if explicit:
        return explicit

    return today_utc() - timedelta(days=max(MAX_RELEASE_AGE_DAYS, 0))


def normalize(text: str | None) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.lower()
    text = re.sub(r"[\u0591-\u05C7]", "", text)
    text = text.replace("&", "and")
    text = re.sub(r"\b(feat|ft|featuring|with|prod|remix|radio edit|single version)\b", " ", text)
    text = re.sub(r"[\s\-\–\—_.,:;!?'\"()\[\]{}|/\\]+", "", text)
    return text


def token_set(text: str | None) -> set[str]:
    cleaned = unicodedata.normalize("NFKC", text or "").lower()
    cleaned = re.sub(r"[\u0591-\u05C7]", "", cleaned)
    cleaned = re.sub(r"[^0-9a-z\u0590-\u05ff]+", " ", cleaned)
    return {token for token in cleaned.split() if len(token) >= 2}


def contains_hebrew(text: str | None) -> bool:
    return bool(re.search(r"[\u0590-\u05ff]", text or ""))


def split_clean_words(text: str | None) -> list[str]:
    cleaned = unicodedata.normalize("NFKC", text or "")
    cleaned = re.sub(r"[\u0591-\u05C7]", "", cleaned)
    cleaned = re.sub(r"[^0-9a-zA-Z\u0590-\u05ff]+", " ", cleaned)
    return [word.strip() for word in cleaned.split() if word.strip()]


def parse_count(value: Any) -> int:
    if value is None:
        return 0

    if isinstance(value, int):
        return max(value, 0)

    if isinstance(value, float):
        return max(int(value), 0)

    text = str(value).strip().lower()
    if not text:
        return 0

    multiplier = 1
    if re.search(r"\b(k|thousand)\b", text):
        multiplier = 1_000
    elif re.search(r"\b(m|million)\b", text):
        multiplier = 1_000_000
    elif re.search(r"\b(b|billion)\b", text):
        multiplier = 1_000_000_000

    match = re.search(r"(\d+(?:[.,]\d+)?)", text.replace(",", "."))
    if not match:
        digits = re.sub(r"\D+", "", text)
        return int(digits) if digits else 0

    return int(float(match.group(1)) * multiplier)


def best_thumbnail_url(value: Any) -> str | None:
    thumbnails = value or []

    if isinstance(thumbnails, dict):
        thumbnails = thumbnails.get("thumbnails") or thumbnails.get("sources") or []

    if not isinstance(thumbnails, list):
        return None

    urls: list[tuple[int, str]] = []
    for thumbnail in thumbnails:
        if not isinstance(thumbnail, dict):
            continue

        url = thumbnail.get("url")
        if not url:
            continue

        width = int(thumbnail.get("width") or 0)
        height = int(thumbnail.get("height") or 0)
        urls.append((width * height, url))

    if not urls:
        return None

    return sorted(urls, key=lambda item: item[0], reverse=True)[0][1]


def extract_artist_stats_text(artist_data: dict[str, Any]) -> str | None:
    candidates = [
        artist_data.get("subscribers"),
        artist_data.get("views"),
        artist_data.get("monthlyListeners"),
        artist_data.get("monthlyListenerCount"),
        artist_data.get("monthlyListenersText"),
        artist_data.get("description"),
    ]

    for candidate in candidates:
        if isinstance(candidate, str) and parse_count(candidate) > 0:
            return candidate

    return None


def add_likely_latin_vowels(value: str) -> list[str]:
    variants = [value]

    if value.endswith("mr") and len(value) >= 4:
        variants.append(value[:-1] + "er")

    if value.endswith("n") and "ii" in value:
        variants.append(value.replace("ii", "ei"))
        variants.append(value.replace("ii", "ey"))
        variants.append(value.replace("ii", "ai"))

    if value.endswith("n") and "iy" in value:
        variants.append(value.replace("iy", "ei"))
        variants.append(value.replace("iy", "ey"))

    return list(dict.fromkeys([variant for variant in variants if variant]))


def transliterate_hebrew_word(word: str, max_variants: int = 8) -> list[str]:
    word = re.sub(r"[\u0591-\u05C7]", "", word or "").strip()

    if not word:
        return []

    if word in HEBREW_NAME_ALIASES:
        return HEBREW_NAME_ALIASES[word][:max_variants]

    chunk_variants: list[list[str]] = []
    index = 0
    while index < len(word):
        two = word[index : index + 2]

        if two == "יי":
            chunk_variants.append(["ei", "ey", "ai", "ay", "y", "i"])
            index += 2
            continue

        if two == "וי":
            chunk_variants.append(["oy", "oi", "uy", "ui"])
            index += 2
            continue

        if two == "או":
            chunk_variants.append(["o", "u", "au"])
            index += 2
            continue

        char = word[index]
        replacements = HEBREW_LETTER_ALIASES.get(char)
        if not replacements:
            replacements = [char.lower()]
        chunk_variants.append(replacements)
        index += 1

    variants = [""]
    for replacements in chunk_variants:
        next_variants: list[str] = []
        for base in variants:
            for replacement in replacements:
                next_variants.extend(add_likely_latin_vowels(base + replacement))
        variants = list(dict.fromkeys(next_variants))[: max_variants * 3]

    variants = [variant for variant in variants if variant]
    return list(dict.fromkeys(variants))[:max_variants]


def combine_word_variants(word_variants: list[list[str]], max_aliases: int) -> list[str]:
    aliases = [""]

    for variants in word_variants:
        next_aliases: list[str] = []
        for prefix in aliases:
            for variant in variants:
                combined = f"{prefix} {variant}".strip()
                next_aliases.append(combined)
        aliases = list(dict.fromkeys(next_aliases))[:max_aliases]

    return [alias for alias in aliases if alias][:max_aliases]


def auto_transliteration_aliases(
    hebrew_name: str,
    max_aliases: int = MAX_AUTO_ALIASES_PER_ARTIST,
) -> list[str]:
    if not ENABLE_HEBREW_TRANSLITERATION:
        return []

    if not contains_hebrew(hebrew_name):
        return []

    words = split_clean_words(hebrew_name)
    if not words:
        return []

    word_variants: list[list[str]] = []
    for word in words:
        if contains_hebrew(word):
            variants = transliterate_hebrew_word(word, max_variants=6)
        else:
            variants = [word.lower()]

        if variants:
            word_variants.append(variants)

    aliases = combine_word_variants(word_variants, max_aliases=max_aliases)
    aliases = [alias.strip().lower() for alias in aliases if alias.strip()]
    return list(dict.fromkeys(aliases))[:max_aliases]


def build_artist_aliases(base_name: str, manual_aliases: list[str]) -> tuple[list[str], list[str]]:
    aliases: list[str] = []
    auto_aliases: list[str] = []

    for alias in [base_name, *manual_aliases]:
        if alias and alias not in aliases:
            aliases.append(alias)

    for source_name in [base_name, *manual_aliases]:
        for auto_alias in auto_transliteration_aliases(source_name):
            if auto_alias and auto_alias not in aliases:
                aliases.append(auto_alias)
                auto_aliases.append(auto_alias)

    max_total = 1 + len(manual_aliases) + MAX_AUTO_ALIASES_PER_ARTIST
    return aliases[:max_total], auto_aliases[:MAX_AUTO_ALIASES_PER_ARTIST]


def latin_phonetic_token(token: str) -> str:
    token = unicodedata.normalize("NFKC", token or "").lower()
    token = re.sub(r"[^0-9a-z]+", "", token)
    token = token.replace("c", "k")
    token = token.replace("ph", "f")
    token = token.replace("qu", "k")
    token = token.replace("ck", "k")
    token = re.sub(r"[aeiouy]+", "", token)
    return token


def phonetic_token_set(text: str | None) -> set[str]:
    tokens = token_set(text)
    phonetic: set[str] = set()
    for token in tokens:
        if re.search(r"[a-z]", token):
            value = latin_phonetic_token(token)
            if len(value) >= 2:
                phonetic.add(value)
    return phonetic


def rapid_fuzz_similarity_score(expected: str, candidate: str) -> int:
    if not ENABLE_RAPIDFUZZ or not RAPIDFUZZ_AVAILABLE or not expected or not candidate:
        return 0

    expected_text = unicodedata.normalize("NFKC", expected or "").lower()
    candidate_text = unicodedata.normalize("NFKC", candidate or "").lower()

    expected_compact = normalize(expected_text)
    candidate_compact = normalize(candidate_text)

    raw_score = max(
        fuzz.ratio(expected_compact, candidate_compact),
        fuzz.partial_ratio(expected_compact, candidate_compact),
        fuzz.token_sort_ratio(expected_text, candidate_text),
        fuzz.token_set_ratio(expected_text, candidate_text),
    )

    if raw_score >= 96:
        return 60
    if raw_score >= 90:
        return 54
    if raw_score >= 84:
        return 48
    if raw_score >= 76:
        return 38
    if raw_score >= 66:
        return 28
    if raw_score >= 55:
        return 16
    return 0


def base_text_similarity_score(expected: str, candidate: str) -> int:
    expected_n = normalize(expected)
    candidate_n = normalize(candidate)

    if not expected_n or not candidate_n:
        return 0

    if expected_n == candidate_n:
        return 60

    if expected_n in candidate_n or candidate_n in expected_n:
        return 48

    expected_tokens = token_set(expected)
    candidate_tokens = token_set(candidate)

    if expected_tokens and candidate_tokens:
        overlap = len(expected_tokens & candidate_tokens)
        union = len(expected_tokens | candidate_tokens)
        ratio = overlap / union if union else 0

        if ratio >= 0.75:
            return 42
        if ratio >= 0.50:
            return 30
        if ratio >= 0.33:
            return 18

    expected_phonetic = phonetic_token_set(expected)
    candidate_phonetic = phonetic_token_set(candidate)

    if expected_phonetic and candidate_phonetic:
        overlap = len(expected_phonetic & candidate_phonetic)
        union = len(expected_phonetic | candidate_phonetic)
        ratio = overlap / union if union else 0

        if ratio >= 1.0:
            return 44
        if ratio >= 0.67:
            return 34
        if ratio >= 0.50:
            return 24

    return 0


def text_similarity_score(expected: str, candidate: str) -> int:
    scores = [
        base_text_similarity_score(expected, candidate),
        rapid_fuzz_similarity_score(expected, candidate),
    ]

    if contains_hebrew(expected):
        for alias in auto_transliteration_aliases(expected, max_aliases=8):
            scores.append(base_text_similarity_score(alias, candidate))
            scores.append(rapid_fuzz_similarity_score(alias, candidate))

    if contains_hebrew(candidate):
        for alias in auto_transliteration_aliases(candidate, max_aliases=8):
            scores.append(base_text_similarity_score(expected, alias))
            scores.append(rapid_fuzz_similarity_score(expected, alias))

    return max(scores) if scores else 0


def phonetic_token_overlap_score(expected_alias: str, candidate_name: str) -> int:
    expected_tokens = phonetic_token_set(expected_alias)
    candidate_tokens = phonetic_token_set(candidate_name)

    if not expected_tokens or not candidate_tokens:
        return 0

    overlap = len(expected_tokens & candidate_tokens)
    ratio = overlap / max(len(expected_tokens), 1)

    if ratio >= 1.0:
        return 32
    if ratio >= 0.67:
        return 25
    if ratio >= 0.50 and len(expected_tokens) >= 2:
        return 18

    if overlap == 1 and len(expected_tokens) >= 2:
        return 8

    return 0


def token_overlap_score(expected_alias: str, candidate_name: str) -> int:
    expected_tokens = token_set(expected_alias)
    candidate_tokens = token_set(candidate_name)

    if not expected_tokens or not candidate_tokens:
        return 0

    overlap = len(expected_tokens & candidate_tokens)
    ratio = overlap / max(len(expected_tokens), 1)

    if ratio >= 1.0:
        return 35
    if ratio >= 0.67:
        return 28
    if ratio >= 0.50 and len(expected_tokens) >= 2:
        return 20

    if overlap == 1 and len(expected_tokens) >= 2:
        return 10

    return 0


def artist_match_score(artist_aliases: list[str], candidate_artist_name: str) -> int:
    if not candidate_artist_name:
        return 0

    best = 0
    candidate_n = normalize(candidate_artist_name)

    for alias in artist_aliases:
        alias_n = normalize(alias)
        if not alias_n:
            continue

        if alias_n == candidate_n:
            best = max(best, 35)
            continue

        alias_tokens = token_set(alias)
        if len(alias_tokens) >= 2 and (alias_n in candidate_n or candidate_n in alias_n):
            best = max(best, 28)
            continue

        best = max(best, token_overlap_score(alias, candidate_artist_name))
        best = max(best, phonetic_token_overlap_score(alias, candidate_artist_name))
        best = max(best, min(text_similarity_score(alias, candidate_artist_name), 24))

    return best


def candidate_match_score(
    title: str,
    artist_aliases: list[str],
    candidate: dict[str, Any],
    expected_type: str,
) -> tuple[int, dict[str, Any]]:
    candidate_title = candidate.get("collectionName") or candidate.get("trackName") or ""
    candidate_artist = candidate.get("artistName") or ""

    title_score = text_similarity_score(title, candidate_title)
    artist_score = artist_match_score(artist_aliases, candidate_artist)

    score = title_score + artist_score

    wrapper_type = candidate.get("wrapperType")
    kind = candidate.get("kind")

    if expected_type == "ALBUM" and wrapper_type == "collection":
        score += 6

    if expected_type == "SINGLE" and kind == "song":
        score += 6

    artist_gate_passed = artist_score >= MIN_ARTIST_MATCH_SCORE
    title_gate_passed = title_score >= MIN_TITLE_MATCH_SCORE

    if not artist_gate_passed or not title_gate_passed:
        score = min(score, MIN_MATCH_SCORE - 1)

    return score, {
        "titleScore": title_score,
        "artistScore": artist_score,
        "artistGatePassed": artist_gate_passed,
        "titleGatePassed": title_gate_passed,
        "candidateTitle": candidate_title,
        "candidateArtist": candidate_artist,
        "wrapperType": wrapper_type,
        "kind": kind,
        "rapidfuzzEnabled": bool(ENABLE_RAPIDFUZZ and RAPIDFUZZ_AVAILABLE),
    }


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


def load_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Could not read JSON file {path}: {exc}")
        return default


def write_json_file(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_artist_sources() -> dict[str, Any]:
    data = load_json_file(ARTIST_SOURCES_FILE, {})
    return data if isinstance(data, dict) else {}


def artist_config(artist: dict[str, str], sources: dict[str, Any]) -> dict[str, Any]:
    config = sources.get(artist["channelId"]) or {}
    if not isinstance(config, dict):
        config = {}

    manual_aliases = config.get("aliases") or []
    if not isinstance(manual_aliases, list):
        manual_aliases = []

    manual_aliases = [str(value).strip() for value in manual_aliases if str(value).strip()]
    base_name = str(config.get("name") or artist["name"]).strip()
    aliases, auto_aliases = build_artist_aliases(base_name, manual_aliases)

    return {
        "name": base_name,
        "aliases": aliases,
        "manualAliases": manual_aliases,
        "autoAliases": auto_aliases,
        "homeFeedEnabled": bool(config.get("homeFeedEnabled", True)),
    }


def sleep_youtube() -> None:
    if YOUTUBE_REQUEST_DELAY_SECONDS > 0:
        time.sleep(YOUTUBE_REQUEST_DELAY_SECONDS)


def sleep_itunes() -> None:
    if ITUNES_REQUEST_DELAY_SECONDS > 0:
        time.sleep(ITUNES_REQUEST_DELAY_SECONDS)


def iTunes_artwork_url(candidate: dict[str, Any], size: int = 1000) -> str | None:
    url = candidate.get("artworkUrl100") or candidate.get("artworkUrl60") or candidate.get("artworkUrl30")
    if not url:
        return None

    return re.sub(r"/\d+x\d+bb\.", f"/{size}x{size}bb.", url)


def iTunes_release_date(candidate: dict[str, Any]) -> str | None:
    raw = candidate.get("releaseDate")
    parsed = parse_iso_date(raw)
    return parsed.isoformat() if parsed else None


def iTunes_result_type(candidate: dict[str, Any], expected_type: str) -> str:
    if candidate.get("kind") == "song":
        return "SINGLE"

    if candidate.get("wrapperType") == "collection":
        if expected_type == "SINGLE":
            return "SINGLE"
        return "ALBUM"

    return expected_type


def read_youtube_artist_data(
    ytmusic: YTMusic,
    artist: dict[str, str],
    report: dict[str, Any],
) -> dict[str, Any] | None:
    channel_id = artist["channelId"]
    artist_name = artist["name"]

    try:
        artist_data = ytmusic.get_artist(channel_id)
        report["artistNetworkReads"] += 1
        sleep_youtube()
        return artist_data if isinstance(artist_data, dict) else None
    except Exception as exc:
        report["artistReadErrors"] += 1
        report["warnings"].append(
            {
                "type": "artist_read_failed",
                "artistName": artist_name,
                "artistChannelId": channel_id,
                "message": str(exc).splitlines()[0][:300],
            }
        )
        print(f"Failed to read YouTube artist: {artist_name}")
        sleep_youtube()
        return None


def get_artist_category_items(
    ytmusic: YTMusic,
    artist_channel_id: str,
    artist_data: dict[str, Any],
    category_key: str,
    report: dict[str, Any],
) -> list[dict[str, Any]]:
    category = artist_data.get(category_key) or {}
    results = category.get("results") or []

    browse_id = category.get("browseId") or artist_channel_id
    params = category.get("params")

    if browse_id and params:
        try:
            expanded = ytmusic.get_artist_albums(
                browse_id,
                params,
                limit=ARTIST_ALBUMS_LIMIT,
                order="Recency",
            )
            if isinstance(expanded, list) and expanded:
                results = expanded
        except Exception as exc:
            report["youtubeExpandErrors"] += 1
            report["warnings"].append(
                {
                    "type": "youtube_expand_failed",
                    "artistChannelId": artist_channel_id,
                    "category": category_key,
                    "message": str(exc).splitlines()[0][:300],
                }
            )
            print(f"Could not expand {category_key} for {artist_channel_id}")

        sleep_youtube()

    return list(results)[:MAX_ITEMS_PER_ARTIST_CATEGORY]


def get_youtube_artist_items(
    ytmusic: YTMusic,
    artist: dict[str, str],
    artist_data: dict[str, Any],
    report: dict[str, Any],
) -> list[dict[str, Any]]:
    channel_id = artist["channelId"]

    items: list[dict[str, Any]] = []

    for category_key, expected_type in (("albums", "ALBUM"), ("singles", "SINGLE")):
        category_items = get_artist_category_items(
            ytmusic=ytmusic,
            artist_channel_id=channel_id,
            artist_data=artist_data,
            category_key=category_key,
            report=report,
        )

        if expected_type == "ALBUM":
            report["youtubeAlbumSourceItems"] += len(category_items)
        else:
            report["youtubeSingleSourceItems"] += len(category_items)

        for item in category_items:
            if not isinstance(item, dict):
                continue

            title = item.get("title")
            browse_id = item.get("browseId")

            if not title or not browse_id:
                report["itemsSkippedMissingBrowseIdOrTitle"] += 1
                continue

            items.append(
                {
                    "expectedType": expected_type,
                    "title": title,
                    "browseId": browse_id,
                    "videoId": item.get("videoId"),
                    "sourceItem": item,
                }
            )

    return items


def first_youtube_track_video_id(
    ytmusic: YTMusic,
    browse_id: str,
    youtube_album_cache: dict[str, Any],
    report: dict[str, Any],
) -> str | None:
    if not ENABLE_YOUTUBE_DRILLDOWN_FOR_VIDEO_ID:
        return None

    if not REFRESH_YOUTUBE_CACHE and browse_id in youtube_album_cache:
        cached = youtube_album_cache.get(browse_id)
        if isinstance(cached, dict):
            return cached.get("firstVideoId")

    try:
        album_details = ytmusic.get_album(browse_id)
        tracks = album_details.get("tracks") or []
        video_id = None

        for track in tracks:
            if isinstance(track, dict) and track.get("videoId"):
                video_id = track["videoId"]
                break

        youtube_album_cache[browse_id] = {
            "firstVideoId": video_id,
            "updatedAt": utc_now_iso(),
        }

        report["youtubeAlbumDrilldownReads"] += 1
        sleep_youtube()
        return video_id
    except Exception as exc:
        report["youtubeAlbumDrilldownErrors"] += 1
        report["warnings"].append(
            {
                "type": "youtube_album_drilldown_failed",
                "browseId": browse_id,
                "message": str(exc).splitlines()[0][:300],
            }
        )
        sleep_youtube()
        return None


def cache_key_for_search(aliases: list[str], title: str, expected_type: str) -> str:
    return json.dumps(
        {
            "scriptVersion": "itunes_hebrew_transliteration_rapidfuzz_v4_popular",
            "aliases": aliases[:MAX_SEARCH_ALIASES_PER_ITEM],
            "title": title,
            "expectedType": expected_type,
            "country": ITUNES_COUNTRY,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def itunes_request(
    params: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any] | None:
    url = "https://itunes.apple.com/search"

    for attempt in range(ITUNES_MAX_RETRIES + 1):
        response = requests.get(url, params=params, timeout=30)

        if response.status_code == 429:
            report["itunes429Count"] += 1
            retry_after = response.headers.get("Retry-After")
            wait_seconds = int(retry_after) if retry_after and retry_after.isdigit() else ITUNES_429_SLEEP_SECONDS
            print(f"iTunes rate limited. Sleeping {wait_seconds}s")
            time.sleep(wait_seconds)
            continue

        if response.status_code >= 500 and attempt < ITUNES_MAX_RETRIES:
            time.sleep(10 * (attempt + 1))
            continue

        if response.status_code != 200:
            report["itunesRequestErrors"] += 1
            report["warnings"].append(
                {
                    "type": "itunes_request_failed",
                    "statusCode": response.status_code,
                    "params": params,
                    "body": response.text[:300],
                }
            )
            sleep_itunes()
            return None

        sleep_itunes()
        return response.json()

    report["itunesRequestErrors"] += 1
    return None


def search_itunes_by_artist_and_title(
    aliases: list[str],
    title: str,
    expected_type: str,
    itunes_lookup_cache: dict[str, Any],
    report: dict[str, Any],
) -> list[dict[str, Any]]:
    key = cache_key_for_search(aliases, title, expected_type)

    if not REFRESH_ITUNES_CACHE and key in itunes_lookup_cache:
        cached = itunes_lookup_cache.get(key)
        report["itunesCacheHits"] += 1
        return cached if isinstance(cached, list) else []

    if MAX_ITUNES_LOOKUPS_TOTAL > 0 and report["itunesNetworkReads"] >= MAX_ITUNES_LOOKUPS_TOTAL:
        report["itunesLookupsSkippedByLimit"] += 1
        return []

    entity = "album" if expected_type == "ALBUM" else "song,album"
    all_candidates: list[dict[str, Any]] = []

    search_aliases = aliases[:MAX_SEARCH_ALIASES_PER_ITEM]

    for alias in search_aliases:
        if MAX_ITUNES_LOOKUPS_TOTAL > 0 and report["itunesNetworkReads"] >= MAX_ITUNES_LOOKUPS_TOTAL:
            report["itunesLookupsSkippedByLimit"] += 1
            break

        term = f"{alias} {title}".strip()

        data = itunes_request(
            params={
                "term": term,
                "media": "music",
                "entity": entity,
                "country": ITUNES_COUNTRY,
                "limit": "10",
            },
            report=report,
        )
        report["itunesNetworkReads"] += 1

        if not data:
            continue

        results = data.get("results") or []
        if isinstance(results, list):
            all_candidates.extend(results)

    unique: dict[str, dict[str, Any]] = {}
    for candidate in all_candidates:
        candidate_id = candidate.get("collectionId") or candidate.get("trackId")
        if candidate_id:
            unique[str(candidate_id)] = candidate

    candidates = list(unique.values())
    itunes_lookup_cache[key] = candidates
    return candidates


def select_best_itunes_candidate(
    title: str,
    artist_aliases: list[str],
    expected_type: str,
    candidates: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, int, dict[str, Any] | None]:
    best_candidate = None
    best_score = -1
    best_details = None

    for candidate in candidates:
        if expected_type == "ALBUM" and candidate.get("wrapperType") != "collection":
            continue

        score, details = candidate_match_score(
            title=title,
            artist_aliases=artist_aliases,
            candidate=candidate,
            expected_type=expected_type,
        )

        if score > best_score:
            best_candidate = candidate
            best_score = score
            best_details = details

    if best_candidate and best_score >= MIN_MATCH_SCORE:
        return best_candidate, best_score, best_details

    return None, best_score, best_details


def build_feed_item(
    artist: dict[str, str],
    youtube_item: dict[str, Any],
    itunes_candidate: dict[str, Any],
    match_score: int,
    ytmusic: YTMusic,
    youtube_album_cache: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any] | None:
    release_date = iTunes_release_date(itunes_candidate)
    if not release_date:
        report["itemsSkippedMissingItunesReleaseDate"] += 1
        return None

    if parse_iso_date(release_date) < cutoff_date():
        report["itemsSkippedOldRelease"] += 1
        return None

    expected_type = youtube_item["expectedType"]
    item_type = iTunes_result_type(itunes_candidate, expected_type)

    title = itunes_candidate.get("collectionName") or itunes_candidate.get("trackName") or youtube_item["title"]
    browse_id = youtube_item["browseId"]

    video_id = youtube_item.get("videoId")
    if item_type == "SINGLE" and not video_id:
        video_id = first_youtube_track_video_id(
            ytmusic=ytmusic,
            browse_id=browse_id,
            youtube_album_cache=youtube_album_cache,
            report=report,
        )

    return {
        "type": item_type,
        "title": title,
        "artistName": artist["name"],
        "artistChannelId": artist["channelId"],
        "youtubeId": browse_id,
        "youtubeBrowseId": browse_id,
        "youtubeVideoId": video_id,
        "itunesCollectionId": itunes_candidate.get("collectionId"),
        "itunesTrackId": itunes_candidate.get("trackId"),
        "itunesUrl": itunes_candidate.get("collectionViewUrl") or itunes_candidate.get("trackViewUrl"),
        "itunesArtistName": itunes_candidate.get("artistName"),
        "releaseDate": release_date,
        "releaseDatePrecision": "day",
        "artworkUrl": iTunes_artwork_url(itunes_candidate),
        "source": "itunes",
        "confidence": "high" if match_score >= 90 else "medium",
        "matchScore": match_score,
        "itunesWrapperType": itunes_candidate.get("wrapperType"),
        "itunesKind": itunes_candidate.get("kind"),
        "trackCount": itunes_candidate.get("trackCount"),
        "primaryGenreName": itunes_candidate.get("primaryGenreName"),
    }


def build_popular_artist_item(artist: dict[str, str], artist_data: dict[str, Any]) -> dict[str, Any]:
    stats_text = extract_artist_stats_text(artist_data)
    monthly_listeners = parse_count(stats_text)

    return {
        "name": artist_data.get("name") or artist_data.get("artist") or artist["name"],
        "channelId": artist["channelId"],
        "thumbnailUrl": best_thumbnail_url(artist_data.get("thumbnails")),
        "monthlyListenersText": stats_text,
        "monthlyListeners": monthly_listeners,
        "source": "youtube_music_artist_page",
    }


def build_popular_song_items(artist: dict[str, str], artist_data: dict[str, Any]) -> list[dict[str, Any]]:
    songs_section = artist_data.get("songs") or {}
    results = songs_section.get("results") or []

    if not isinstance(results, list):
        return []

    artist_score = parse_count(extract_artist_stats_text(artist_data))
    if artist_score <= 0:
        artist_score = 1

    items: list[dict[str, Any]] = []
    for index, item in enumerate(results[:POPULAR_SONGS_PER_ARTIST], start=1):
        if not isinstance(item, dict):
            continue

        title = item.get("title")
        video_id = item.get("videoId")
        if not title or not video_id:
            continue

        thumbnails = item.get("thumbnails") or item.get("thumbnail")
        monthly_plays_text = item.get("views") or item.get("playCount") or item.get("plays")
        monthly_plays = parse_count(monthly_plays_text)

        rank_score = monthly_plays if monthly_plays > 0 else max(artist_score - index, 1)

        items.append(
            {
                "title": title,
                "artistName": artist["name"],
                "artistChannelId": artist["channelId"],
                "youtubeVideoId": video_id,
                "youtubeId": video_id,
                "artworkUrl": best_thumbnail_url(thumbnails),
                "monthlyPlaysText": monthly_plays_text,
                "monthlyPlays": rank_score,
                "source": "youtube_music_artist_songs",
                "sourceRank": index,
            }
        )

    return items


def dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}

    for item in items:
        key = str(item.get("itunesTrackId") or item.get("itunesCollectionId") or item.get("youtubeBrowseId"))
        if not key:
            key = "|".join(
                [
                    item.get("artistChannelId", ""),
                    item.get("type", ""),
                    normalize(item.get("title", "")),
                ]
            )

        existing = unique.get(key)
        if not existing:
            unique[key] = item
            continue

        if item.get("matchScore", 0) > existing.get("matchScore", 0):
            unique[key] = item

    return list(unique.values())


def dedupe_popular_artists(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}

    for item in items:
        channel_id = item.get("channelId")
        if not channel_id:
            continue

        existing = unique.get(channel_id)
        if not existing or item.get("monthlyListeners", 0) > existing.get("monthlyListeners", 0):
            unique[channel_id] = item

    return sorted(
        unique.values(),
        key=lambda item: (
            item.get("monthlyListeners", 0),
            item.get("name", ""),
        ),
        reverse=True,
    )[:MAX_POPULAR_ARTISTS]


def dedupe_popular_songs(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}

    for item in items:
        key = item.get("youtubeVideoId") or "|".join(
            [
                item.get("artistChannelId", ""),
                normalize(item.get("title", "")),
            ]
        )

        existing = unique.get(key)
        if not existing or item.get("monthlyPlays", 0) > existing.get("monthlyPlays", 0):
            unique[key] = item

    return sorted(
        unique.values(),
        key=lambda item: (
            item.get("monthlyPlays", 0),
            item.get("artistName", ""),
            item.get("title", ""),
        ),
        reverse=True,
    )[:MAX_POPULAR_SONGS]


def sort_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            item.get("releaseDate", "0000-00-00"),
            item.get("matchScore", 0),
            item.get("type", ""),
            item.get("title", ""),
        ),
        reverse=True,
    )


def initial_report(allowed_artists_count: int) -> dict[str, Any]:
    return {
        "generatedAt": utc_now_iso(),
        "strategy": "itunes_metadata_with_youtube_playback_ids_and_hebrew_transliteration",
        "scriptVersion": "itunes_hebrew_transliteration_rapidfuzz_v4_popular",
        "allowedArtistsCount": allowed_artists_count,
        "itunesCountry": ITUNES_COUNTRY,
        "maxItemsPerArtistCategory": MAX_ITEMS_PER_ARTIST_CATEGORY,
        "artistAlbumsLimit": ARTIST_ALBUMS_LIMIT,
        "maxPopularArtists": MAX_POPULAR_ARTISTS,
        "maxPopularSongs": MAX_POPULAR_SONGS,
        "popularSongsPerArtist": POPULAR_SONGS_PER_ARTIST,
        "maxReleaseAgeDays": MAX_RELEASE_AGE_DAYS,
        "minReleaseDate": MIN_RELEASE_DATE or None,
        "minMatchScore": MIN_MATCH_SCORE,
        "minArtistMatchScore": MIN_ARTIST_MATCH_SCORE,
        "minTitleMatchScore": MIN_TITLE_MATCH_SCORE,
        "enableRapidFuzz": ENABLE_RAPIDFUZZ,
        "rapidFuzzAvailable": RAPIDFUZZ_AVAILABLE,
        "enableHebrewTransliteration": ENABLE_HEBREW_TRANSLITERATION,
        "maxAutoAliasesPerArtist": MAX_AUTO_ALIASES_PER_ARTIST,
        "maxSearchAliasesPerItem": MAX_SEARCH_ALIASES_PER_ITEM,
        "youtubeRequestDelaySeconds": YOUTUBE_REQUEST_DELAY_SECONDS,
        "itunesRequestDelaySeconds": ITUNES_REQUEST_DELAY_SECONDS,
        "itunes429SleepSeconds": ITUNES_429_SLEEP_SECONDS,
        "itunesMaxRetries": ITUNES_MAX_RETRIES,
        "maxItunesLookupsTotal": MAX_ITUNES_LOOKUPS_TOTAL,
        "artistNetworkReads": 0,
        "artistReadErrors": 0,
        "youtubeExpandErrors": 0,
        "youtubeAlbumSourceItems": 0,
        "youtubeSingleSourceItems": 0,
        "youtubePopularSongSourceItems": 0,
        "popularArtistsGenerated": 0,
        "popularSongsGenerated": 0,
        "youtubeAlbumDrilldownReads": 0,
        "youtubeAlbumDrilldownErrors": 0,
        "itunesNetworkReads": 0,
        "itunesCacheHits": 0,
        "itunes429Count": 0,
        "itunesRequestErrors": 0,
        "itunesLookupsSkippedByLimit": 0,
        "itemsSkippedMissingBrowseIdOrTitle": 0,
        "itemsSkippedNoItunesCandidate": 0,
        "itemsSkippedWeakItunesCandidate": 0,
        "itemsSkippedMissingItunesReleaseDate": 0,
        "itemsSkippedOldRelease": 0,
        "itemsGeneratedBeforeDedupe": 0,
        "itemsGeneratedAfterDedupe": 0,
        "albumsGeneratedAfterDedupe": 0,
        "singlesGeneratedAfterDedupe": 0,
        "artistsWithAutoAliases": [],
        "autoAliasExamples": [],
        "weakMatches": [],
        "warnings": [],
    }


def main() -> None:
    artists = parse_allowed_artists()
    sources = load_artist_sources()
    report = initial_report(len(artists))

    print(f"Loaded allowed artists: {len(artists)}")
    print("iTunes is the metadata source. YouTube Music is used for artist shelves and playable IDs.")
    print(f"iTunes country: {ITUNES_COUNTRY}")
    print(f"iTunes request delay: {ITUNES_REQUEST_DELAY_SECONDS}s")
    print(f"Hebrew transliteration enabled: {ENABLE_HEBREW_TRANSLITERATION}")
    print(f"Cutoff date: {cutoff_date().isoformat()}")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    itunes_lookup_cache = load_json_file(ITUNES_LOOKUP_CACHE_FILE, {})
    youtube_album_cache = load_json_file(YOUTUBE_ALBUM_CACHE_FILE, {})

    if not isinstance(itunes_lookup_cache, dict):
        itunes_lookup_cache = {}
    if not isinstance(youtube_album_cache, dict):
        youtube_album_cache = {}

    ytmusic = YTMusic()
    feed_items: list[dict[str, Any]] = []
    popular_artist_items: list[dict[str, Any]] = []
    popular_song_items: list[dict[str, Any]] = []

    for index, artist in enumerate(artists, start=1):
        config = artist_config(artist, sources)

        if not config["homeFeedEnabled"]:
            continue

        aliases = config["aliases"]

        if config.get("autoAliases"):
            report["artistsWithAutoAliases"].append(
                {
                    "artistName": artist["name"],
                    "youtubeChannelId": artist["channelId"],
                    "autoAliases": config["autoAliases"][:MAX_AUTO_ALIASES_PER_ARTIST],
                }
            )
            if len(report["autoAliasExamples"]) < 20:
                report["autoAliasExamples"].append(
                    {
                        "artistName": artist["name"],
                        "aliasesUsed": aliases[:MAX_SEARCH_ALIASES_PER_ITEM],
                    }
                )

        print(f"[{index}/{len(artists)}] {artist['name']} | aliases: {len(aliases)}")

        artist_data = read_youtube_artist_data(
            ytmusic=ytmusic,
            artist=artist,
            report=report,
        )

        if not artist_data:
            continue

        popular_artist_items.append(build_popular_artist_item(artist, artist_data))
        artist_popular_songs = build_popular_song_items(artist, artist_data)
        popular_song_items.extend(artist_popular_songs)
        report["youtubePopularSongSourceItems"] += len(artist_popular_songs)

        youtube_items = get_youtube_artist_items(
            ytmusic=ytmusic,
            artist=artist,
            artist_data=artist_data,
            report=report,
        )

        for youtube_item in youtube_items:
            if not ENABLE_NAME_MATCH:
                continue

            title = youtube_item["title"]
            expected_type = youtube_item["expectedType"]

            candidates = search_itunes_by_artist_and_title(
                aliases=aliases,
                title=title,
                expected_type=expected_type,
                itunes_lookup_cache=itunes_lookup_cache,
                report=report,
            )

            if not candidates:
                report["itemsSkippedNoItunesCandidate"] += 1
                continue

            itunes_candidate, match_score, match_details = select_best_itunes_candidate(
                title=title,
                artist_aliases=aliases,
                expected_type=expected_type,
                candidates=candidates,
            )

            if not itunes_candidate:
                report["itemsSkippedWeakItunesCandidate"] += 1
                report["weakMatches"].append(
                    {
                        "artistName": artist["name"],
                        "artistChannelId": artist["channelId"],
                        "aliasesUsed": aliases[:MAX_SEARCH_ALIASES_PER_ITEM],
                        "title": title,
                        "expectedType": expected_type,
                        "bestScore": match_score,
                        "details": match_details,
                    }
                )
                continue

            feed_item = build_feed_item(
                artist=artist,
                youtube_item=youtube_item,
                itunes_candidate=itunes_candidate,
                match_score=match_score,
                ytmusic=ytmusic,
                youtube_album_cache=youtube_album_cache,
                report=report,
            )

            if feed_item:
                feed_items.append(feed_item)

    report["itemsGeneratedBeforeDedupe"] = len(feed_items)
    feed_items = sort_items(dedupe_items(feed_items))
    popular_artist_items = dedupe_popular_artists(popular_artist_items)
    popular_song_items = dedupe_popular_songs(popular_song_items)
    report["popularArtistsGenerated"] = len(popular_artist_items)
    report["popularSongsGenerated"] = len(popular_song_items)
    report["itemsGeneratedAfterDedupe"] = len(feed_items)
    report["albumsGeneratedAfterDedupe"] = sum(1 for item in feed_items if item.get("type") == "ALBUM")
    report["singlesGeneratedAfterDedupe"] = sum(1 for item in feed_items if item.get("type") == "SINGLE")
    report["completedAt"] = utc_now_iso()

    feed = {
        "version": 8,
        "generatedAt": report["generatedAt"],
        "source": "itunes_youtube_music",
        "strategy": "itunes_metadata_youtube_playback_ids_hebrew_transliteration_popular_rankings",
        "allowedArtistsCount": len(artists),
        "itemsCount": len(feed_items),
        "albumsCount": report["albumsGeneratedAfterDedupe"],
        "singlesCount": report["singlesGeneratedAfterDedupe"],
        "popularArtistsCount": len(popular_artist_items),
        "popularSongsCount": len(popular_song_items),
        "items": feed_items,
        "popularArtists": popular_artist_items,
        "popularSongs": popular_song_items,
    }

    write_json_file(OUTPUT_FILE, feed)
    write_json_file(REPORT_FILE, report)
    write_json_file(ITUNES_LOOKUP_CACHE_FILE, itunes_lookup_cache)
    write_json_file(YOUTUBE_ALBUM_CACHE_FILE, youtube_album_cache)

    print(f"Generated {OUTPUT_FILE} with {len(feed_items)} items.")
    print(f"Albums: {report['albumsGeneratedAfterDedupe']}")
    print(f"Singles: {report['singlesGeneratedAfterDedupe']}")
    print(f"Popular artists: {report['popularArtistsGenerated']}")
    print(f"Popular songs: {report['popularSongsGenerated']}")
    print(f"iTunes network reads: {report['itunesNetworkReads']}")
    print(f"iTunes cache hits: {report['itunesCacheHits']}")
    print(f"iTunes 429 count: {report['itunes429Count']}")


if __name__ == "__main__":
    main()
