"""Keyword dictionaries for the community chat-history analysis pipeline.

Each dictionary maps a canonical label -> a list of pattern strings.
Patterns are matched case-insensitively as whole-word / whole-phrase regex.
Non-ASCII terms (any script -- CJK, Cyrillic, Arabic, etc.) match verbatim;
ASCII terms match as word-boundaries.

Used by analyze.py's keyword-extraction stage.

CUSTOMIZE THIS FILE for your own community. The entries below are a
Rust programming language community example -- replace with your own
community's actual terms.

See config/templates/ for ready-made keyword sets for common scenarios
(AI product, programming language, gaming community).
"""

from __future__ import annotations

import re

# ----------------------------------------------------------------------------
# 1. Mentions -- what tools/products do users name?
# ----------------------------------------------------------------------------
PROVIDERS: dict[str, list[str]] = {
    "cargo": ["cargo"],
    "rustup": ["rustup"],
    "rust_analyzer": ["rust-analyzer", "rust analyzer"],
    "clippy": ["clippy"],
    "rustfmt": ["rustfmt"],
    "miri": ["miri"],
    "tokio": ["tokio"],
    "actix": ["actix"],
    "axum": ["axum"],
    "bevy": ["bevy"],
    "wasm_bindgen": ["wasm-bindgen", "wasm bindgen"],
}

# ----------------------------------------------------------------------------
# 2. Alternatives -- competing products/languages
# ----------------------------------------------------------------------------
COMPETITORS: dict[str, list[str]] = {
    "go": [r"\bgo(lang)?\b"],
    "zig": [r"\bzig\b"],
    "cpp": [r"\bc\+\+\b", r"\bcpp\b"],
    "python": [r"\bpython\b"],
    "ocaml": [r"\bocaml\b"],
    "swift": [r"\bswift\b"],
    "kotlin": [r"\bkotlin\b"],
}

# ----------------------------------------------------------------------------
# 3. Platforms -- where do users discuss?
# ----------------------------------------------------------------------------
MESSAGING: dict[str, list[str]] = {
    "discord": ["discord"],
    "zulip": ["zulip"],
    "reddit": ["reddit", "r/rust"],
    "github_discussions": ["github discussions", "github issues"],
    "stackoverflow": [r"\bstack\s?overflow\b"],
    "mastodon": ["mastodon"],
    "youtube": ["youtube", r"\byt\b"],
}

# ----------------------------------------------------------------------------
# 4. Topic mentions -- what features/concepts do users talk about?
# ----------------------------------------------------------------------------
PRODUCT_FEATURES: dict[str, list[str]] = {
    "borrow_checker": ["borrow checker", "borrow check"],
    "lifetimes": [r"\blifetimes?\b"],
    "async_await": [r"\basync\b", r"\bawait\b"],
    "traits": [r"\btraits?\b"],
    "macros": [r"\bmacros?\b"],
    "pattern_matching": ["pattern matching", r"\bmatch\b"],
    "ownership": ["ownership"],
    "unsafe": [r"\bunsafe\b"],
    "generics": [r"\bgenerics?\b"],
    "error_handling": [r"\bResult\b", r"\bOption\b"],
}

# ----------------------------------------------------------------------------
# 5. Setup methods -- how do users install/set up?
# ----------------------------------------------------------------------------
INSTALL: dict[str, list[str]] = {
    "rustup": ["rustup", "rustup install"],
    "apt": [r"\bapt\b"],
    "homebrew": ["brew", "homebrew"],
    "docker": [r"\bdocker\b"],
    "nix": [r"\bnix\b"],
    "wsl": [r"\bwsl\b"],
    "from_source": ["from source", "build from source"],
    "macos": ["macos", "mac os", r"\bosx\b", r"\bbrew\b"],
    "linux_native": ["ubuntu", "debian", "arch", "fedora"],
}

# ----------------------------------------------------------------------------
# 6. Pain points -- errors, failures, help-requests
# ----------------------------------------------------------------------------
FRICTION: dict[str, list[str]] = {
    "compile_error": ["compile error", "won't compile", "compilation failed"],
    "borrow_checker_fight": ["borrow checker", "fighting the borrow"],
    "lifetime_error": ["lifetime error", "lifetime mismatch"],
    "slow_compile": ["slow compile", "compile time", "build time"],
    "dependency_hell": ["dependency hell", "version conflict"],
    "confused": [r"\bhow\b", r"\bwhat\b", r"\bwhy\b"],
    "error_generic": [r"\berror\b", r"\bfail", r"\bbroken\b", r"\bcrash\b"],
    "install_issue": ["install", "setup"],
    "documentation_gap": ["no docs", "documentation", "unclear docs"],
}

# ----------------------------------------------------------------------------
# 7. Impersonator / suspicious domains
# ----------------------------------------------------------------------------
IMPERSONATOR_DOMAINS: list[str] = [
    "rust-lang.com",
    "rustlang.org",
    "rust-download.com",
]

OFFICIAL_DOMAINS: list[str] = [
    "rust-lang.org",
    "doc.rust-lang.org",
    "crates.io",
    "lib.rs",
]

# ----------------------------------------------------------------------------
# 8. Discovery channels -- how did users find the community?
# ----------------------------------------------------------------------------
ACQUISITION: dict[str, list[str]] = {
    "friend": ["friend told", "recommended by"],
    "blog": [r"\bblog\b"],
    "conference": ["conference", "rustconf"],
    "course": [r"\bcourse\b", "university"],
    "work": ["at work", "company uses"],
}

# ----------------------------------------------------------------------------
# URL extraction
# ----------------------------------------------------------------------------
URL_PATTERN = re.compile(r"https?://[^\s)>\],'\"]+", re.IGNORECASE)

# ----------------------------------------------------------------------------
# Question detection -- per-language heuristics.
# ----------------------------------------------------------------------------
QUESTION_PATTERN_EN = re.compile(
    r"[?]\s*$|\b(how|what|when|where|why|which|who|is it|can i|can you|does|do i|should i)\b",
    re.IGNORECASE,
)

QUESTION_PATTERNS_BY_LANGUAGE: dict[str, re.Pattern] = {
    "zh": re.compile(r"[？?]\s*$|怎么|怎样|如何|什么|为什么|可以吗|能不能"),
    "ja": re.compile(r"[？?]\s*$|どう|なぜ|何|ですか|ますか"),
    "ko": re.compile(r"[？?]\s*$|어떻게|왜|무엇|인가요|나요"),
    "ru": re.compile(r"[?]\s*$|как\b|почему\b|что\b|где\b", re.IGNORECASE),
    "es": re.compile(
        r"[?¿]\s*$|cómo\b|qué\b|por qué\b|cuándo\b|dónde\b", re.IGNORECASE
    ),
    "fr": re.compile(
        r"[?]\s*$|comment\b|pourquoi\b|quoi\b|quand\b|où\b", re.IGNORECASE
    ),
    "de": re.compile(r"[?]\s*$|wie\b|warum\b|was\b|wann\b|wo\b", re.IGNORECASE),
    "pt": re.compile(r"[?]\s*$|como\b|por que\b|quando\b|onde\b", re.IGNORECASE),
    "ar": re.compile(r"[؟?]\s*$|كيف|لماذا|ماذا|متى|أين"),
}


def question_pattern_for(language_code: str | None) -> re.Pattern:
    """Return the compiled question-detection pattern for a target language."""
    lang_pat = QUESTION_PATTERNS_BY_LANGUAGE.get(language_code or "")
    if lang_pat is None:
        return QUESTION_PATTERN_EN
    combined = f"(?:{QUESTION_PATTERN_EN.pattern})|(?:{lang_pat.pattern})"
    return re.compile(combined, re.IGNORECASE)


QUESTION_PATTERN = QUESTION_PATTERN_EN


# ----------------------------------------------------------------------------
# Compile helpers
# ----------------------------------------------------------------------------
def _compile_dict(d: dict[str, list[str]]) -> dict[str, list[re.Pattern]]:
    """Compile each pattern list into regex."""
    compiled: dict[str, list[re.Pattern]] = {}
    for label, patterns in d.items():
        compiled_patterns = []
        for p in patterns:
            if p.startswith(r"\b") or p.startswith(r"("):
                compiled_patterns.append(re.compile(p, re.IGNORECASE))
            elif re.search(r"[^\x00-\x7f]", p):
                compiled_patterns.append(re.compile(re.escape(p), re.IGNORECASE))
            else:
                compiled_patterns.append(
                    re.compile(rf"(?<!\w){re.escape(p)}(?!\w)", re.IGNORECASE)
                )
        compiled[label] = compiled_patterns
    return compiled


compile_keyword_dict = _compile_dict

PROVIDERS_COMPILED = _compile_dict(PROVIDERS)
COMPETITORS_COMPILED = _compile_dict(COMPETITORS)
MESSAGING_COMPILED = _compile_dict(MESSAGING)
PRODUCT_FEATURES_COMPILED = _compile_dict(PRODUCT_FEATURES)
INSTALL_COMPILED = _compile_dict(INSTALL)
FRICTION_COMPILED = _compile_dict(FRICTION)
ACQUISITION_COMPILED = _compile_dict(ACQUISITION)


def match_any(text: str, compiled: dict[str, list[re.Pattern]]) -> list[str]:
    """Return list of labels whose patterns appear in text."""
    hits = []
    for label, patterns in compiled.items():
        for p in patterns:
            if p.search(text):
                hits.append(label)
                break
    return hits
