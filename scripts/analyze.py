#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Digital Clone Analyzer v2.1
Universal history analyzer for digital-clone skill.
Cross-platform (Windows/macOS/Linux), zero external dependencies.

Analyzes ~/.claude/history.jsonl (or %APPDATA%\claude\history.jsonl on Windows)
to extract personality traits, speaking style, and thinking patterns.
"""

import json
import os
import platform
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Cross-platform paths
# ---------------------------------------------------------------------------

def get_claude_dir() -> Path:
    """Get Claude config directory based on platform."""
    system = platform.system()
    if system == "Windows":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "claude"
        return Path.home() / "AppData" / "Roaming" / "claude"
    else:
        return Path.home() / ".claude"


CLAUDE_DIR = get_claude_dir()
HISTORY_PATH = CLAUDE_DIR / "history.jsonl"
PROFILE_PATH = CLAUDE_DIR / "digital-clone-profile.json"

# ---------------------------------------------------------------------------
# Filter configuration
# ---------------------------------------------------------------------------

MIN_LEN = 4
MAX_LEN = 350
SKIP_PREFIXES = (
    "/", "[Pasted text", "[cccc]", "[HTTP", "[MSW]", "SYSTEM (",
    "```", "Error:", "Warning:", "DEBUG:", "INFO:",
)
NOISE_RE = re.compile(
    r"Error:|Exception:|Traceback|npm ERR|ENOENT|EACCES|EPERM|"
    r"undefined is not|Cannot read prop|TypeError:|SyntaxError:|ReferenceError:|"
    r"at \w+\.\w+\(|\.js:\d+:\d+|\.ts:\d+:\d+|\.py:\d+|"
    r"ModuleNotFoundError|ImportError|KeyError:|ValueError:|"
    r"^\s*\d+\s*\|",  # Line number prefixes from error traces
    re.IGNORECASE
)
JUNK_RE = re.compile(r"^[\s\d\W]{12,}$|^[a-f0-9]{32,}$", re.IGNORECASE)
URL_RE = re.compile(r"https?://\S{50,}")  # Very long URLs

# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

SCRIPT_RANGES = {
    "cjk": [(0x4E00, 0x9FFF), (0x3400, 0x4DBF), (0xF900, 0xFAFF)],
    "ja_hira": [(0x3040, 0x309F)],
    "ja_kata": [(0x30A0, 0x30FF)],
    "ko": [(0xAC00, 0xD7AF), (0x1100, 0x11FF)],
    "cyrillic": [(0x0400, 0x04FF), (0x0500, 0x052F)],
    "arabic": [(0x0600, 0x06FF), (0x0750, 0x077F)],
    "hebrew": [(0x0590, 0x05FF)],
    "thai": [(0x0E00, 0x0E7F)],
    "devanagari": [(0x0900, 0x097F)],
    "latin": [(0x0041, 0x005A), (0x0061, 0x007A), (0x00C0, 0x00FF)],
}


def _char_script(ch: str) -> str:
    cp = ord(ch)
    for script, ranges in SCRIPT_RANGES.items():
        for start, end in ranges:
            if start <= cp <= end:
                return script
    return "other"


def detect_language(texts: list[str]) -> dict:
    """Detect primary and secondary languages from text samples."""
    script_counts: Counter = Counter()
    for t in texts:
        for ch in t:
            script = _char_script(ch)
            if script != "other":
                script_counts[script] += 1

    total = sum(script_counts.values()) or 1
    top = script_counts.most_common(3)

    if not top:
        return {"primary": "en", "secondary": None, "confidence": 0.5}

    # Map scripts to language codes
    script_to_lang = {
        "cjk": "zh", "ja_hira": "ja", "ja_kata": "ja", "ko": "ko",
        "cyrillic": "ru", "arabic": "ar", "hebrew": "he",
        "thai": "th", "devanagari": "hi", "latin": "en",
    }

    primary_script, primary_count = top[0]
    primary_lang = script_to_lang.get(primary_script, "other")
    confidence = round(primary_count / total, 2)

    # Detect mixed language
    secondary = None
    if len(top) > 1:
        sec_script, sec_count = top[1]
        if sec_count / total > 0.15:
            secondary = script_to_lang.get(sec_script)

    # Special case: CJK + Latin mix
    if primary_script == "cjk" and secondary == "en":
        return {"primary": "zh", "secondary": "en", "mixed": True, "confidence": confidence}
    if primary_script == "latin" and len(top) > 1 and top[1][0] == "cjk":
        return {"primary": "en", "secondary": "zh", "mixed": True, "confidence": confidence}

    return {
        "primary": primary_lang,
        "secondary": secondary,
        "mixed": secondary is not None,
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# Tokenization
# ---------------------------------------------------------------------------

def tokenize(text: str, lang: str) -> list[str]:
    """Language-aware tokenization. No external dependencies."""
    tokens = []

    if lang in ("zh", "ja"):
        # CJK: character bigrams + full words + Latin words
        for match in re.finditer(r'[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]+|[a-zA-Z][a-zA-Z0-9_.-]*', text):
            word = match.group()
            if re.match(r'[a-zA-Z]', word):
                tokens.append(word.lower())
            else:
                # Bigrams for CJK
                for i in range(len(word) - 1):
                    tokens.append(word[i:i + 2])
                # Also keep full short words
                if 2 <= len(word) <= 4:
                    tokens.append(word)
    else:
        # Latin-based: word tokenization
        for word in re.findall(r"[a-zA-Z][a-zA-Z0-9'_.-]*", text.lower()):
            if len(word) > 1:
                tokens.append(word)

    return tokens


# ---------------------------------------------------------------------------
# Communication patterns (multilingual)
# ---------------------------------------------------------------------------

PATTERNS = [
    # Imperative / action requests
    (re.compile(r"^(help|fix|check|show|add|create|make|write|run|test|build|install|update|remove|delete|get|set|find|search)\b", re.I),
     "imperative-start", "action-oriented"),
    (re.compile(r"^(帮我|请帮|帮忙|麻烦|幫我|請幫)"), "request-prefix", "polite-request"),
    (re.compile(r"^(ayuda|aide|hilf|помоги|助けて|도와)", re.I), "request-prefix", "polite-request"),

    # Questions
    (re.compile(r"^(why|为什么|為什麼|왜|なぜ|почему|pourquoi|warum|por ?qu[eé])\b", re.I),
     "why-question", "analytical"),
    (re.compile(r"^(how|如何|怎[么麼]|어떻게|どうやって|как|comment|wie|cómo)\b", re.I),
     "how-question", "process-oriented"),
    (re.compile(r"^(what|什[么麼]|뭐|何|что|qu[oe]i?|was)\b", re.I),
     "what-question", "information-seeking"),
    (re.compile(r"^(where|哪[里裡]|어디|どこ|где|où|wo|dónde)\b", re.I),
     "where-question", "location-seeking"),
    (re.compile(r"^(when|什[么麼]时候|언제|いつ|когда|quand|wann|cuándo)\b", re.I),
     "when-question", "time-seeking"),

    # Ability/permission requests
    (re.compile(r"^(can you|could you|would you|能不能|可[以不]可以|할 수 있|できる)", re.I),
     "can-you-request", "permission-seeking"),

    # Constraints and preferences
    (re.compile(r"(don'?t|do not|不要|不用|别|別|하지.?마|やめて|ne\s+(pas|fais)|nicht|no\s+hagas)", re.I),
     "negation-constraint", "boundary-setting"),
    (re.compile(r"^(just|only|只|仅|僅|只需|只要|solo|nur|ただ|seulement|just)\b", re.I),
     "simplify-constraint", "minimalist"),
    (re.compile(r"(instead|而不是|改成|대신|代わりに|plutôt|statt|en lugar)", re.I),
     "change-request", "modification"),
    (re.compile(r"(must|should|have to|必须|必須|应该|應該|해야|しなければ|muss|doit|debe)", re.I),
     "requirement-statement", "directive"),

    # Flow control
    (re.compile(r"^(continue|go on|继续|繼續|계속|続けて|continuer|weiter|continúa)", re.I),
     "continue-request", "flow-control"),
    (re.compile(r"^(stop|wait|pause|停|等|멈춰|止まって|arrête|stopp|para)", re.I),
     "stop-request", "flow-control"),
    (re.compile(r"^(never\s*mind|forget|算了|취소|やっぱり|annuler|egal|olvida)", re.I),
     "retract", "reconsideration"),
    (re.compile(r"(还是|還是|or rather|actually|其实|其實|사실|実は)", re.I),
     "correction", "reconsideration"),

    # Confirmation
    (re.compile(r"^(ok|okay|yes|sure|好|行|是|네|はい|oui|ja|sí|да)\s*[,.]?\s*$", re.I),
     "confirmation", "agreement"),
    (re.compile(r"^(no|nope|不|否|아니|いいえ|non|nein|нет)\s*[,.]?\s*$", re.I),
     "rejection", "disagreement"),

    # Emotional expressions
    (re.compile(r"(thanks|thank you|谢谢|謝謝|고마워|ありがとう|merci|danke|gracias|спасибо)", re.I),
     "gratitude", "positive-emotion"),
    (re.compile(r"(sorry|抱歉|对不起|對不起|미안|すみません|désolé|entschuldigung|perdón|извини)", re.I),
     "apology", "politeness"),
    (re.compile(r"(!{2,}|\?{2,}|\.{3,}|。{2,}|…)", re.I),
     "emphasis-punctuation", "expressive"),
]


def extract_patterns(texts: list[str]) -> list[dict]:
    """Extract communication patterns with examples."""
    counts: Counter = Counter()
    categories: Counter = Counter()
    examples: dict[str, list[str]] = defaultdict(list)

    for t in texts:
        for regex, label, category in PATTERNS:
            if regex.search(t):
                counts[label] += 1
                categories[category] += 1
                if len(examples[label]) < 3:
                    examples[label].append(t[:100])

    patterns = [
        {
            "pattern": label,
            "frequency": count,
            "examples": examples.get(label, []),
        }
        for label, count in counts.most_common(20) if count >= 2
    ]

    return patterns, dict(categories.most_common(10))


# ---------------------------------------------------------------------------
# Style metrics
# ---------------------------------------------------------------------------

# Polite markers by language
POLITE_MARKERS = {
    "zh": ["请", "請", "您", "麻烦", "麻煩", "劳驾", "勞駕", "谢谢", "謝謝"],
    "en": ["please", "could you", "would you", "kindly", "if you don't mind", "thank you"],
    "ja": ["ください", "お願い", "いただけ", "ありがとう", "すみません"],
    "ko": ["주세요", "부탁", "감사", "죄송"],
    "es": ["por favor", "gracias", "podría", "sería tan amable"],
    "fr": ["s'il vous plaît", "merci", "pourriez-vous", "veuillez"],
    "de": ["bitte", "danke", "könnten Sie", "würden Sie"],
    "ru": ["пожалуйста", "спасибо", "не могли бы", "будьте добры"],
}

# Hedging/uncertainty markers
HEDGE_MARKERS = {
    "zh": ["可能", "也许", "或许", "大概", "好像", "似乎", "应该"],
    "en": ["maybe", "perhaps", "might", "probably", "i think", "i guess", "sort of", "kind of"],
    "ja": ["かもしれない", "たぶん", "おそらく", "と思う"],
    "ko": ["아마", "어쩌면", "것 같아"],
}


def compute_style(texts: list[str], lang_info: dict) -> dict:
    """Compute speaking style metrics."""
    n = max(len(texts), 1)
    primary_lang = lang_info.get("primary", "en")

    # Basic metrics
    lengths = [len(t) for t in texts]
    avg_len = sum(lengths) / n
    median_len = sorted(lengths)[n // 2] if lengths else 0

    # Punctuation analysis
    end_chars = [t.rstrip()[-1:] for t in texts if t.strip()]
    period_endings = sum(1 for c in end_chars if c in ".。！!？?")
    question_endings = sum(1 for c in end_chars if c in "?？")
    exclaim_endings = sum(1 for c in end_chars if c in "!！")
    no_punct = sum(1 for c in end_chars if c.isalnum())

    end_punct_style = "formal" if period_endings / n > 0.5 else "none" if no_punct / n > 0.6 else "casual"

    # Formality: polite markers
    markers = POLITE_MARKERS.get(primary_lang, POLITE_MARKERS["en"])
    polite_count = sum(1 for t in texts for m in markers if m.lower() in t.lower())
    formality = round(min(1.0, polite_count / n * 2.5), 2)

    # Directness: imperative starts, short sentences, action verbs first
    direct_starters = [
        "帮我", "直接", "把", "删", "改", "写", "做", "用", "看", "查",
        "fix", "add", "run", "check", "just", "remove", "update", "show", "get", "set",
        "make", "create", "delete", "find", "tell", "give", "send",
    ]
    imperative_count = sum(1 for t in texts if any(t.lower().startswith(w) for w in direct_starters))
    short_and_direct = sum(1 for t in texts if len(t) < 40 and not any(h in t.lower() for h in HEDGE_MARKERS.get(primary_lang, [])))
    directness = round(min(1.0, (imperative_count + short_and_direct * 0.5) / n * 1.8), 2)

    # Hedging (uncertainty)
    hedge_words = HEDGE_MARKERS.get(primary_lang, HEDGE_MARKERS["en"])
    hedge_count = sum(1 for t in texts for h in hedge_words if h.lower() in t.lower())
    certainty = round(max(0.0, 1.0 - hedge_count / n * 3), 2)

    # Question ratio
    question_ratio = round(question_endings / n, 2) if n > 0 else 0

    # Expressiveness (exclamations, emphasis)
    expressive_count = exclaim_endings + sum(1 for t in texts if re.search(r'[!！]{2,}|[?？]{2,}|\.{3,}|…', t))
    expressiveness = round(min(1.0, expressive_count / n * 4), 2)

    return {
        "formality": formality,
        "directness": directness,
        "certainty": certainty,
        "expressiveness": expressiveness,
        "questionRatio": question_ratio,
        "avgMessageLength": round(avg_len),
        "medianMessageLength": median_len,
        "usesPoliteMarkers": formality > 0.25,
        "endPunctuation": end_punct_style,
        "language": lang_info,
    }


# ---------------------------------------------------------------------------
# Temporal analysis
# ---------------------------------------------------------------------------

def analyze_temporal(entries: list[dict]) -> dict:
    """Analyze usage patterns over time."""
    if not entries:
        return {}

    hours: Counter = Counter()
    days: Counter = Counter()
    months: Counter = Counter()

    for e in entries:
        ts = e.get("timestamp", 0)
        if ts > 0:
            try:
                dt = datetime.fromtimestamp(ts / 1000)
                hours[dt.hour] += 1
                days[dt.strftime("%A")] += 1
                months[dt.strftime("%Y-%m")] += 1
            except (OSError, ValueError):
                continue

    # Find peak hours
    peak_hours = [h for h, _ in hours.most_common(5)]
    active_period = "night" if any(h in peak_hours for h in [22, 23, 0, 1, 2, 3]) else \
                    "morning" if any(h in peak_hours for h in [6, 7, 8, 9, 10]) else \
                    "afternoon" if any(h in peak_hours for h in [12, 13, 14, 15, 16]) else \
                    "evening"

    return {
        "peakHours": peak_hours,
        "activePeriod": active_period,
        "mostActiveDay": days.most_common(1)[0][0] if days else None,
        "activityByMonth": dict(months.most_common(12)),
    }


# ---------------------------------------------------------------------------
# Vocabulary analysis
# ---------------------------------------------------------------------------

# Common stopwords (multilingual)
STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could", "should",
    "may", "might", "must", "shall", "can", "need", "dare", "ought", "used",
    "to", "of", "in", "for", "on", "with", "at", "by", "from", "as", "into",
    "through", "during", "before", "after", "above", "below", "between",
    "and", "but", "or", "nor", "so", "yet", "both", "either", "neither",
    "not", "only", "own", "same", "than", "too", "very", "just",
    "this", "that", "these", "those", "it", "its",
    "i", "me", "my", "myself", "we", "our", "ours", "ourselves",
    "you", "your", "yours", "yourself", "yourselves",
    "he", "him", "his", "himself", "she", "her", "hers", "herself",
    "they", "them", "their", "theirs", "themselves",
    "what", "which", "who", "whom", "whose",
    "here", "there", "when", "where", "why", "how",
    "all", "each", "every", "both", "few", "more", "most", "other", "some", "such",
    "no", "any", "if", "then", "else", "because", "about", "also",
    "的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一", "这", "中",
    "大", "为", "上", "个", "国", "说", "到", "会", "可", "也", "你", "对", "生", "能",
    "子", "那", "得", "于", "着", "下", "自", "之", "年", "过", "发", "后", "作", "里",
}


def analyze_vocabulary(texts: list[str], lang: str) -> dict:
    """Analyze vocabulary patterns."""
    all_tokens: Counter = Counter()
    for t in texts:
        for tok in tokenize(t, lang):
            if tok.lower() not in STOPWORDS and len(tok) > 1:
                all_tokens[tok] += 1

    # Top tokens
    top_words = [w for w, c in all_tokens.most_common(50) if c >= 2]

    # Find repeated phrases (n-grams that appear 3+ times)
    phrase_counter: Counter = Counter()
    for t in texts:
        # Extract 4-20 char substrings
        for length in range(4, min(21, len(t) + 1)):
            for i in range(len(t) - length + 1):
                sub = t[i:i + length].strip()
                if len(sub) >= 4 and not sub.isspace() and not sub.isdigit():
                    phrase_counter[sub] += 1

    # Deduplicate: keep longer phrases, remove substrings
    phrases_raw = [(p, c) for p, c in phrase_counter.most_common(300) if c >= 3]
    custom_phrases = []
    for phrase, count in phrases_raw:
        # Skip if this phrase is a substring of an already-added longer phrase
        if not any(phrase in existing and phrase != existing for existing in custom_phrases):
            # Skip if mostly stopwords or very short words
            words = phrase.split()
            if not all(w.lower() in STOPWORDS for w in words if len(w) > 1):
                custom_phrases.append(phrase)
        if len(custom_phrases) >= 20:
            break

    # Vocabulary richness (type-token ratio approximation)
    total_tokens = sum(all_tokens.values())
    unique_tokens = len(all_tokens)
    richness = round(unique_tokens / max(total_tokens, 1) * 100, 1)

    return {
        "topTokens": top_words[:35],
        "customPhrases": custom_phrases,
        "vocabularySize": unique_tokens,
        "totalTokens": total_tokens,
        "richnessScore": richness,
    }


# ---------------------------------------------------------------------------
# Topic and interest detection
# ---------------------------------------------------------------------------

def detect_topics(texts: list[str], projects: list[str]) -> dict:
    """Extract topics from content and project contexts."""
    # Extract from project paths
    path_tokens: Counter = Counter()
    # Common path segments to ignore (not meaningful for topic detection)
    ignored_segments = {
        "home", "users", "user", "documents", "coding", "code", "projects", "project",
        "app", "apps", "temp", "tmp", "src", "lib", "bin", "var", "opt", "usr",
        "desktop", "downloads", "appdata", "roaming", "local", ".config", ".claude",
        "work", "workspace", "dev", "development", "repos", "repository", "git",
        Path.home().name.lower(),  # Current user's home directory name
    }
    for p in projects:
        for seg in re.split(r'[/\\]', p.lower()):
            if len(seg) > 2 and seg not in ignored_segments and not seg.startswith("."):
                path_tokens[seg] += 1

    # Extract from message content
    word_freq: Counter = Counter()
    for t in texts:
        for w in re.findall(r'[a-zA-Z][a-zA-Z0-9_.-]{2,}', t.lower()):
            if w not in STOPWORDS and len(w) > 2:
                word_freq[w] += 1

    # Merge: project context weighted higher
    combined = Counter()
    for k, v in path_tokens.items():
        combined[k] += v * 4
    for k, v in word_freq.items():
        combined[k] += v

    # Filter noise
    noise_terms = {"pasted", "text", "lines", "error", "file", "https", "http", "www", "com"}
    topics = [(k, v) for k, v in combined.most_common(80) if k not in noise_terms and v >= 2]

    return {
        "topKeywords": [k for k, _ in topics[:25]],
        "projectContexts": [k for k, _ in path_tokens.most_common(20) if path_tokens[k] >= 2],
        "techIndicators": _detect_tech_stack(texts, projects),
    }


def _detect_tech_stack(texts: list[str], projects: list[str]) -> list[str]:
    """Detect technology stack from content."""
    tech_patterns = {
        "Python": [r"\bpython\b", r"\bpip\b", r"\buv\b", r"\.py\b", r"\bfastapi\b", r"\bdjango\b", r"\bflask\b"],
        "JavaScript": [r"\bjavascript\b", r"\bnode\b", r"\bnpm\b", r"\bpnpm\b", r"\bbun\b", r"\.js\b"],
        "TypeScript": [r"\btypescript\b", r"\.ts\b", r"\.tsx\b"],
        "React": [r"\breact\b", r"\bnextjs\b", r"\bnext\.js\b", r"\.jsx\b"],
        "Vue": [r"\bvue\b", r"\bnuxt\b", r"\.vue\b"],
        "Rust": [r"\brust\b", r"\bcargo\b", r"\.rs\b"],
        "Go": [r"\bgolang\b", r"\bgo\s+build\b", r"\.go\b"],
        "Docker": [r"\bdocker\b", r"\bcontainer\b", r"dockerfile"],
        "Git": [r"\bgit\b", r"\bgithub\b", r"\bgitlab\b"],
        "Linux": [r"\blinux\b", r"\bubuntu\b", r"\barch\b", r"\bsystemd\b"],
        "AWS": [r"\baws\b", r"\bs3\b", r"\bec2\b", r"\blambda\b"],
        "Database": [r"\bsql\b", r"\bpostgres\b", r"\bmysql\b", r"\bmongodb\b", r"\bredis\b"],
        "AI/ML": [r"\bopenai\b", r"\bclaude\b", r"\bllm\b", r"\bgpt\b", r"\bml\b", r"\bai\b"],
        "Tailwind": [r"\btailwind\b", r"\btailwindcss\b"],
        "CSS": [r"\bcss\b", r"\bscss\b", r"\bsass\b", r"\bstyles?\b"],
    }

    all_text = " ".join(texts + projects).lower()
    detected = []
    for tech, patterns in tech_patterns.items():
        for pattern in patterns:
            if re.search(pattern, all_text, re.I):
                detected.append(tech)
                break

    return detected


# ---------------------------------------------------------------------------
# Sample selection
# ---------------------------------------------------------------------------

def select_samples(texts: list[str], patterns: list[dict]) -> list[str]:
    """Select diverse representative samples."""
    samples = []
    seen = set()

    # One example per detected pattern
    for p in patterns:
        for ex in p.get("examples", []):
            clean = ex.strip()
            if clean and clean not in seen and len(clean) > 8:
                samples.append(clean)
                seen.add(clean)
                break
        if len(samples) >= 12:
            break

    # Add diverse length samples
    short_samples = [t for t in texts if 10 < len(t) < 40 and t not in seen]
    medium_samples = [t for t in texts if 40 <= len(t) < 80 and t not in seen]
    long_samples = [t for t in texts if 80 <= len(t) < 150 and t not in seen]

    for pool in [short_samples[:5], medium_samples[:5], long_samples[:3]]:
        for t in pool:
            if t not in seen:
                samples.append(t)
                seen.add(t)
            if len(samples) >= 25:
                break

    return samples[:25]


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def load_history(since_ts: int = 0) -> list[dict]:
    """Load and filter history entries."""
    if not HISTORY_PATH.exists():
        return []

    entries = []
    # Handle potential encoding issues on Windows
    encodings = ["utf-8", "utf-8-sig", "gbk", "latin-1"]

    for encoding in encodings:
        try:
            with open(HISTORY_PATH, "r", encoding=encoding, errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    ts = entry.get("timestamp", 0)
                    if ts <= since_ts:
                        continue

                    text = entry.get("display", "")
                    if _is_valid(text):
                        entries.append({
                            "text": text,
                            "timestamp": ts,
                            "project": entry.get("project", ""),
                        })
            break  # Success
        except UnicodeDecodeError:
            continue

    return entries


def _is_valid(text: str) -> bool:
    """Check if message is valid for analysis."""
    if not text or len(text) < MIN_LEN or len(text) > MAX_LEN:
        return False
    for pfx in SKIP_PREFIXES:
        if text.startswith(pfx):
            return False
    if NOISE_RE.search(text):
        return False
    if JUNK_RE.match(text):
        return False
    if URL_RE.search(text):
        return False
    return bool(text.strip())


def _count_total_lines() -> int:
    """Count total lines in history file."""
    if not HISTORY_PATH.exists():
        return 0
    count = 0
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8", errors="replace") as f:
            for _ in f:
                count += 1
    except Exception:
        pass
    return count


def build_profile(entries: list[dict]) -> dict:
    """Build complete personality profile."""
    texts = [e["text"] for e in entries]
    projects = list(set(e["project"] for e in entries if e["project"]))

    # Analysis
    lang_info = detect_language(texts)
    primary_lang = lang_info.get("primary", "en")
    style = compute_style(texts, lang_info)
    patterns, categories = extract_patterns(texts)
    vocab = analyze_vocabulary(texts, primary_lang)
    topics = detect_topics(texts, projects)
    temporal = analyze_temporal(entries)
    samples = select_samples(texts, patterns)

    # Timestamps
    timestamps = [e["timestamp"] for e in entries if e.get("timestamp")]
    min_ts = min(timestamps) if timestamps else 0
    max_ts = max(timestamps) if timestamps else 0

    # Thinking style inference
    n = max(len(texts), 1)
    pragmatic_patterns = {"imperative-start", "request-prefix", "simplify-constraint"}
    iterative_patterns = {"retract", "correction", "continue-request"}
    analytical_patterns = {"why-question", "how-question", "what-question"}

    pragmatic_score = sum(p["frequency"] for p in patterns if p["pattern"] in pragmatic_patterns)
    iterative_score = sum(p["frequency"] for p in patterns if p["pattern"] in iterative_patterns)
    analytical_score = sum(p["frequency"] for p in patterns if p["pattern"] in analytical_patterns)

    return {
        "version": "2.1.0",
        "generator": "digital-clone-analyzer",
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "lastUpdated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "lastAnalyzedTimestamp": max_ts,
        "platform": platform.system(),
        "dataSource": {
            "historyPath": str(HISTORY_PATH),
            "totalMessages": _count_total_lines(),
            "analyzedMessages": len(entries),
            "filteredOut": _count_total_lines() - len(entries),
            "dateRange": {
                "start": datetime.fromtimestamp(min_ts / 1000).strftime("%Y-%m-%d") if min_ts else "unknown",
                "end": datetime.fromtimestamp(max_ts / 1000).strftime("%Y-%m-%d") if max_ts else "unknown",
            },
        },
        "profile": {
            "speakingStyle": style,
            "vocabulary": vocab,
            "communicationPatterns": patterns,
            "patternCategories": categories,
            "thinkingStyle": {
                "pragmatic": round(min(1.0, pragmatic_score / n * 3), 2),
                "iterative": round(min(1.0, iterative_score / n * 5), 2),
                "analytical": round(min(1.0, analytical_score / n * 3), 2),
                "detailOriented": round(min(1.0, style["avgMessageLength"] / 100), 2),
                "multitasking": round(min(1.0, len(set(projects)) / 10), 2),
            },
            "topics": topics,
            "temporal": temporal,
        },
        "sampleDialogues": samples,
        "learnedPatterns": [],
    }


# ---------------------------------------------------------------------------
# Incremental merge
# ---------------------------------------------------------------------------

def merge_profiles(old: dict, new_data: dict, new_count: int) -> dict:
    """Merge new analysis into existing profile conservatively."""
    merged = json.loads(json.dumps(old))
    op = merged["profile"]
    np_ = new_data["profile"]

    # Style: clamp drift to ±0.1
    for key in ("formality", "directness", "certainty", "expressiveness"):
        if key in op.get("speakingStyle", {}) and key in np_.get("speakingStyle", {}):
            ov = op["speakingStyle"].get(key, 0.5)
            nv = np_["speakingStyle"].get(key, 0.5)
            op["speakingStyle"][key] = round(ov + max(-0.1, min(0.1, nv - ov)), 2)

    # Vocabulary: union
    for vk in ("topTokens", "customPhrases"):
        existing = set(op.get("vocabulary", {}).get(vk, []))
        new_items = [w for w in np_.get("vocabulary", {}).get(vk, []) if w not in existing]
        op["vocabulary"][vk] = op["vocabulary"].get(vk, []) + new_items[:15]

    # Communication patterns: merge frequencies
    existing_map = {p["pattern"]: p for p in op.get("communicationPatterns", [])}
    for np in np_.get("communicationPatterns", []):
        if np["pattern"] in existing_map:
            existing_map[np["pattern"]]["frequency"] += np["frequency"]
            # Update examples if we have new ones
            existing_examples = set(existing_map[np["pattern"]].get("examples", []))
            for ex in np.get("examples", []):
                if ex not in existing_examples and len(existing_map[np["pattern"]]["examples"]) < 5:
                    existing_map[np["pattern"]]["examples"].append(ex)
        else:
            existing_map[np["pattern"]] = np
    op["communicationPatterns"] = sorted(existing_map.values(), key=lambda x: -x.get("frequency", 0))

    # Thinking style: clamp ±0.1
    for key in ("pragmatic", "iterative", "analytical", "detailOriented", "multitasking"):
        if key in op.get("thinkingStyle", {}) and key in np_.get("thinkingStyle", {}):
            ov = op["thinkingStyle"].get(key, 0.5)
            nv = np_["thinkingStyle"].get(key, 0.5)
            op["thinkingStyle"][key] = round(ov + max(-0.1, min(0.1, nv - ov)), 2)

    # Topics: union
    for tk in ("topKeywords", "projectContexts", "techIndicators"):
        existing = set(op.get("topics", {}).get(tk, []))
        for item in np_.get("topics", {}).get(tk, []):
            if item not in existing:
                op["topics"][tk] = op["topics"].get(tk, []) + [item]
                existing.add(item)

    # Samples: append unique, cap at 30
    existing_s = set(merged.get("sampleDialogues", []))
    for s in new_data.get("sampleDialogues", []):
        if s not in existing_s and len(merged["sampleDialogues"]) < 30:
            merged["sampleDialogues"].append(s)
            existing_s.add(s)

    # Record learning event
    changes = {
        "newTokens": [w for w in np_.get("vocabulary", {}).get("topTokens", [])[:10]
                      if w not in set(old.get("profile", {}).get("vocabulary", {}).get("topTokens", []))],
        "newPhrases": [w for w in np_.get("vocabulary", {}).get("customPhrases", [])[:5]
                       if w not in set(old.get("profile", {}).get("vocabulary", {}).get("customPhrases", []))],
        "styleShifts": {
            k: round(op.get("speakingStyle", {}).get(k, 0) - old.get("profile", {}).get("speakingStyle", {}).get(k, 0), 2)
            for k in ("formality", "directness", "certainty")
        },
    }
    merged.setdefault("learnedPatterns", []).append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "messagesAnalyzed": new_count,
        "totalAnalyzed": merged.get("dataSource", {}).get("analyzedMessages", 0) + new_count,
        "changes": changes,
    })

    merged["lastUpdated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    merged["lastAnalyzedTimestamp"] = new_data.get("lastAnalyzedTimestamp", 0)
    merged["dataSource"]["analyzedMessages"] = merged.get("dataSource", {}).get("analyzedMessages", 0) + new_count
    merged["dataSource"]["totalMessages"] = new_data.get("dataSource", {}).get("totalMessages", 0)
    if "dateRange" in new_data.get("dataSource", {}):
        merged["dataSource"]["dateRange"]["end"] = new_data["dataSource"]["dateRange"].get("end", "unknown")

    return merged


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def cmd_init():
    """Initialize: full analysis of all history."""
    print(json.dumps({"status": "analyzing", "path": str(HISTORY_PATH)}), flush=True)

    entries = load_history(since_ts=0)
    if len(entries) < 5:
        print(json.dumps({
            "status": "error",
            "error": f"Insufficient data: only {len(entries)} valid messages found (need ≥5)",
            "historyPath": str(HISTORY_PATH),
            "hint": "Use Claude Code more and try again later",
        }))
        sys.exit(1)

    profile = build_profile(entries)

    # Ensure directory exists
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_PATH.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")

    # Output summary
    s = profile["profile"]["speakingStyle"]
    print(json.dumps({
        "status": "ok",
        "analyzed": len(entries),
        "dateRange": profile["dataSource"]["dateRange"],
        "path": str(PROFILE_PATH),
        "summary": {
            "language": s["language"],
            "formality": s["formality"],
            "directness": s["directness"],
            "certainty": s["certainty"],
            "avgLength": s["avgMessageLength"],
        },
        "topPatterns": [p["pattern"] for p in profile["profile"]["communicationPatterns"][:6]],
        "topKeywords": profile["profile"]["topics"]["topKeywords"][:10],
        "techStack": profile["profile"]["topics"]["techIndicators"][:8],
        "samples": len(profile["sampleDialogues"]),
    }, ensure_ascii=False, indent=2))


def cmd_learn():
    """Incremental learning: analyze new messages only."""
    if not PROFILE_PATH.exists():
        print(json.dumps({
            "status": "error",
            "error": "Profile not found. Run 'init' first.",
            "expectedPath": str(PROFILE_PATH),
        }))
        sys.exit(1)

    old = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    since = old.get("lastAnalyzedTimestamp", 0)

    entries = load_history(since_ts=since)
    if not entries:
        print(json.dumps({
            "status": "no_new_data",
            "lastUpdated": old.get("lastUpdated", "unknown"),
            "totalAnalyzed": old.get("dataSource", {}).get("analyzedMessages", 0),
        }))
        return

    new_data = build_profile(entries)
    merged = merge_profiles(old, new_data, len(entries))
    PROFILE_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

    evt = merged["learnedPatterns"][-1]
    print(json.dumps({
        "status": "ok",
        "newMessages": len(entries),
        "totalAnalyzed": merged["dataSource"]["analyzedMessages"],
        "changes": evt["changes"],
        "learningEvents": len(merged["learnedPatterns"]),
    }, ensure_ascii=False, indent=2))


def cmd_status():
    """Display current profile."""
    if not PROFILE_PATH.exists():
        print(json.dumps({
            "status": "error",
            "error": "Profile not found. Run 'init' first.",
            "expectedPath": str(PROFILE_PATH),
        }))
        sys.exit(1)
    print(PROFILE_PATH.read_text(encoding="utf-8"))


def cmd_export(dest: str = "."):
    """Export profile to specified directory."""
    if not PROFILE_PATH.exists():
        print(json.dumps({"status": "error", "error": "Profile not found."}))
        sys.exit(1)

    import shutil
    out = Path(dest)
    out.mkdir(parents=True, exist_ok=True)
    target = out / "digital-clone-profile.json"
    shutil.copy2(PROFILE_PATH, target)

    # Also create a human-readable summary
    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    summary_path = out / "digital-clone-summary.txt"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(_generate_summary(profile))

    print(json.dumps({
        "status": "ok",
        "profilePath": str(target),
        "summaryPath": str(summary_path),
    }))


def _generate_summary(profile: dict) -> str:
    """Generate human-readable summary."""
    p = profile.get("profile", {})
    s = p.get("speakingStyle", {})
    t = p.get("thinkingStyle", {})
    ds = profile.get("dataSource", {})

    lines = [
        "=" * 50,
        "DIGITAL CLONE PROFILE SUMMARY",
        "=" * 50,
        "",
        f"Generated: {profile.get('created', 'unknown')}",
        f"Platform: {profile.get('platform', 'unknown')}",
        f"Messages Analyzed: {ds.get('analyzedMessages', 0)}",
        f"Date Range: {ds.get('dateRange', {}).get('start', '?')} to {ds.get('dateRange', {}).get('end', '?')}",
        "",
        "SPEAKING STYLE",
        "-" * 30,
        f"  Language: {s.get('language', {}).get('primary', 'unknown')}",
        f"  Formality: {s.get('formality', 0):.0%}",
        f"  Directness: {s.get('directness', 0):.0%}",
        f"  Certainty: {s.get('certainty', 0):.0%}",
        f"  Avg Message Length: {s.get('avgMessageLength', 0)} chars",
        "",
        "THINKING STYLE",
        "-" * 30,
        f"  Pragmatic: {t.get('pragmatic', 0):.0%}",
        f"  Iterative: {t.get('iterative', 0):.0%}",
        f"  Analytical: {t.get('analytical', 0):.0%}",
        "",
        "TOP PATTERNS",
        "-" * 30,
    ]
    for pat in p.get("communicationPatterns", [])[:5]:
        lines.append(f"  {pat.get('pattern', '?')}: {pat.get('frequency', 0)}x")

    lines.extend([
        "",
        "TECH STACK",
        "-" * 30,
        f"  {', '.join(p.get('topics', {}).get('techIndicators', [])[:10])}",
        "",
        "SAMPLE DIALOGUES",
        "-" * 30,
    ])
    for sample in profile.get("sampleDialogues", [])[:5]:
        lines.append(f"  > {sample[:80]}...")

    lines.append("")
    lines.append("=" * 50)
    return "\n".join(lines)


def cmd_info():
    """Show system information and paths."""
    print(json.dumps({
        "platform": platform.system(),
        "pythonVersion": platform.python_version(),
        "claudeDir": str(CLAUDE_DIR),
        "historyPath": str(HISTORY_PATH),
        "historyExists": HISTORY_PATH.exists(),
        "profilePath": str(PROFILE_PATH),
        "profileExists": PROFILE_PATH.exists(),
    }, indent=2))


def main():
    if len(sys.argv) < 2:
        print(f"""
Digital Clone Analyzer v2.1
===========================
Usage: python {sys.argv[0]} <command> [args]

Commands:
  init     - Analyze all history, create new profile
  learn    - Analyze new messages, update profile
  status   - Display current profile (JSON)
  export   - Export profile to directory
  info     - Show system paths and status

Paths:
  History: {HISTORY_PATH}
  Profile: {PROFILE_PATH}
""", file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1].lower()
    dispatch = {
        "init": cmd_init,
        "learn": cmd_learn,
        "status": cmd_status,
        "info": cmd_info,
    }

    if cmd == "export":
        cmd_export(sys.argv[2] if len(sys.argv) > 2 else ".")
    elif cmd in dispatch:
        dispatch[cmd]()
    else:
        print(json.dumps({"status": "error", "error": f"Unknown command: {cmd}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
