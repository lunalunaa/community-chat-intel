"""Language & region profiles for the community chat-analysis pipeline.

Centralizes all language- and region-specific behavior so the pipeline works
for any target-language community:

  - LANGUAGE_PROFILES   : how to detect "target language" vs "other" vs "mixed"
                          per language (script-range ratio for CJK-family /
                          Cyrillic / Arabic / etc., or stopword-ratio for
                          Latin-script languages).
  - REGION_PROFILES     : region-specific "shadow community" platforms
                          (where users hang out outside the analyzed chat)
                          and timezone-bucket definitions for the location
                          proxy (posting-hour → rough-geography heuristic).

Add a new LANGUAGE_PROFILES entry to support a new target language.
Add a new REGION_PROFILES entry to support a new region's shadow-community
platform list and timezone semantics.

Usage: `analyze.py --target-language ja --region jp`, or
`--target-language none` to disable language classification entirely (every
message counts as "target"; useful for already-monolingual exports).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ----------------------------------------------------------------------------
# Language detection profiles
# ----------------------------------------------------------------------------


@dataclass(frozen=True)
class LanguageProfile:
    code: str
    name: str
    # Unicode character-class ranges (as regex character-class bodies, e.g.
    # r"\u4e00-\u9fff") used for script-ratio detection. None means "use
    # stopword-ratio detection instead" (for Latin-script languages where a
    # dedicated Unicode block doesn't exist).
    script_ranges: tuple[str, ...] | None = None
    # Ratio threshold above which a message counts as target-language
    # ("mixed" band starts here; "target" band is ratio >= 0.7 for scripts,
    # or a language-appropriate threshold for stopword-based detection).
    threshold: float = 0.30
    # For stopword-ratio detection only: a set of very common function words.
    # Deliberately short — this is a cheap heuristic, not a language model.
    stopwords: frozenset[str] = field(default_factory=frozenset)

    @property
    def script_pattern(self) -> re.Pattern | None:
        if not self.script_ranges:
            return None
        body = "".join(self.script_ranges)
        return re.compile(f"[{body}]")


LANGUAGE_PROFILES: dict[str, LanguageProfile] = {
    "zh": LanguageProfile(
        "zh",
        "Chinese",
        script_ranges=(r"\u4e00-\u9fff", r"\u3400-\u4dbf"),
        threshold=0.30,
    ),
    "ja": LanguageProfile(
        "ja",
        "Japanese",
        # Hiragana + Katakana + shared CJK ideographs
        script_ranges=(r"\u3040-\u30ff", r"\u4e00-\u9fff"),
        threshold=0.30,
    ),
    "ko": LanguageProfile(
        "ko",
        "Korean",
        script_ranges=(r"\uac00-\ud7a3", r"\u1100-\u11ff"),
        threshold=0.30,
    ),
    "ru": LanguageProfile(
        "ru",
        "Russian",
        script_ranges=(r"\u0400-\u04ff",),
        threshold=0.30,
    ),
    "ar": LanguageProfile(
        "ar",
        "Arabic",
        script_ranges=(r"\u0600-\u06ff",),
        threshold=0.30,
    ),
    "he": LanguageProfile(
        "he",
        "Hebrew",
        script_ranges=(r"\u0590-\u05ff",),
        threshold=0.30,
    ),
    "th": LanguageProfile(
        "th",
        "Thai",
        script_ranges=(r"\u0e00-\u0e7f",),
        threshold=0.30,
    ),
    # Latin-script languages: no dedicated Unicode block to count, so we use
    # a stopword-ratio heuristic instead. Precision is lower than the
    # script-ratio approach (as with the original CJK-only heuristic this
    # pipeline shipped with) — treat as directional, spot-check a sample.
    "es": LanguageProfile(
        "es",
        "Spanish",
        threshold=0.15,
        stopwords=frozenset(
            "que de la el en y a los se del las un por con no una su para es "
            "al lo como más pero sus le ya o este sí porque esta entre cuando "
            "muy sin sobre también me hasta hay donde".split()
        ),
    ),
    "fr": LanguageProfile(
        "fr",
        "French",
        threshold=0.15,
        stopwords=frozenset(
            "le de un être et à il avoir ne je son que se qui ce dans en du "
            "elle au de ce le pour pas vous par sur avec tout faire son mettre "
            "autre on mais nous comme ou si leur y dire".split()
        ),
    ),
    "de": LanguageProfile(
        "de",
        "German",
        threshold=0.15,
        stopwords=frozenset(
            "der die und in den von zu das mit sich des auf für ist im dem "
            "nicht ein eine als auch es an werden aus er hat dass sie nach "
            "wird bei einer um am sind noch wie einem".split()
        ),
    ),
    "pt": LanguageProfile(
        "pt",
        "Portuguese",
        threshold=0.15,
        stopwords=frozenset(
            "de a o que e do da em um para é com não uma os no se na por mais "
            "as dos como mas foi ao ele das tem à seu sua ou ser quando muito "
            "há nos já está eu também só pelo pela".split()
        ),
    ),
    "id": LanguageProfile(
        "id",
        "Indonesian",
        threshold=0.15,
        stopwords=frozenset(
            "yang dan di itu dengan untuk tidak ini dari dalam akan pada "
            "juga saya ke karena tersebut bisa ada mereka lebih atau saat "
            "harus sebagai sudah kita jika".split()
        ),
    ),
    "vi": LanguageProfile(
        "vi",
        "Vietnamese",
        script_ranges=(r"\u1ea0-\u1ef9", r"\u00c0-\u1ef9"),
        threshold=0.05,
    ),
}


def _cjk_family_ratio(text: str, profile: LanguageProfile) -> float:
    stripped = "".join(text.split())
    if not stripped:
        return 0.0
    pattern = profile.script_pattern
    if pattern is None:
        return 0.0
    hits = sum(1 for c in stripped if pattern.match(c))
    return hits / len(stripped)


def _stopword_ratio(text: str, profile: LanguageProfile) -> float:
    tokens = re.findall(r"[a-zà-ÿ]+", text.lower())
    if not tokens:
        return 0.0
    hits = sum(1 for t in tokens if t in profile.stopwords)
    return hits / len(tokens)


def script_ratio(text: str, profile: LanguageProfile) -> float:
    """Fraction of the message that looks like `profile`'s target language."""
    if profile.script_pattern is not None:
        return _cjk_family_ratio(text, profile)
    return _stopword_ratio(text, profile)


def classify_language(text: str, profile: LanguageProfile) -> str:
    """Return one of: 'target', 'mixed', 'other', 'unknown'.

    Same three-tier heuristic, generalized to any registered language profile:
      - ratio >= 0.7                          -> "target"
      - ratio >= profile.threshold            -> "mixed"
      - a handful of target-script hits in a long-enough message
        (heavy code-switching, still counts as target-language content)
                                               -> "mixed"
      - message too short to judge            -> "unknown"
      - otherwise                             -> "other"
    """
    stripped = text.strip()
    if not stripped:
        return "unknown"

    ratio = script_ratio(text, profile)

    if ratio >= 0.7:
        return "target"
    if ratio >= profile.threshold:
        return "mixed"

    if profile.script_pattern is not None:
        hit_count = sum(1 for c in stripped if profile.script_pattern.match(c))
        if hit_count >= 3 and len(stripped) >= 20:
            return "mixed"

    if len(stripped) < 5:
        return "unknown"
    return "other"


# ----------------------------------------------------------------------------
# Region profiles — shadow-community platforms + timezone-proxy buckets
# ----------------------------------------------------------------------------


@dataclass(frozen=True)
class RegionProfile:
    code: str
    name: str
    # label -> list of keyword patterns (same shape as keywords.py dicts)
    shadow_community: dict[str, list[str]]
    # label -> (lo_hour, hi_hour) inclusive UTC-hour ranges used to bucket a
    # user's modal posting hour into a rough-geography cluster. "other" is
    # always the fallback bucket for hours that don't match any range.
    timezone_buckets: dict[str, tuple[int, int]]
    # Provider labels (matching keywords.PROVIDERS keys) considered
    # "regional" for this region, vs. "global" (everything else). Used by
    # crosstabs.py's provider-cluster pivot.
    regional_providers: frozenset[str] = field(default_factory=frozenset)


REGION_PROFILES: dict[str, RegionProfile] = {
    "cn": RegionProfile(
        "cn",
        "Greater China",
        shadow_community={
            "zhihu": ["zhihu", "知乎", "zhuanlan"],
            "wechat_oa": ["公众号", "微信公众号", "official account"],
            "wechat_group": ["微信群", "wechat group"],
            "qq_group": ["qq群", "qq group"],
            "feishu_group": ["飞书群", "feishu group"],
            "bilibili": ["bilibili", "b站", "哔哩哔哩"],
            "xiaohongshu": ["xiaohongshu", "小红书", "rednote"],
            "juejin": ["juejin", "掘金"],
            "csdn": ["csdn"],
            "cnblogs": ["cnblogs", "博客园"],
            "segmentfault": ["segmentfault", "思否"],
            "douyin_tiktok": ["douyin", "抖音", "tiktok"],
            "baidu_baike": ["baidu", "百度", "baike"],
            "github_discussions": ["github discussions", "github issues"],
        },
        timezone_buckets={
            "mainland_evening": (12, 16),  # UTC 12-16 = evening 20-24 Beijing (UTC+8)
            "na_evening": (0, 6),  # UTC 0-6 = evening PT/ET
            "eu_evening": (18, 22),  # UTC 18-22 = evening CET
        },
        regional_providers=frozenset(
            {
                "deepseek",
                "kimi_moonshot",
                "qwen_alibaba",
                "glm_zhipu",
                "minimax",
                "volcengine_ark",
                "doubao",
                "baichuan",
                "yi_01ai",
            }
        ),
    ),
    "jp": RegionProfile(
        "jp",
        "Japan",
        shadow_community={
            "note_jp": ["note.com", "note投稿"],
            "qiita": ["qiita"],
            "zenn": ["zenn.dev", "zenn"],
            "x_japan": ["twitter", "x.com", "ツイッター"],
            "discord_jp": ["discordサーバー", "discord server"],
            "5ch": ["5ch", "2ch", "なんj"],
            "youtube_jp": ["youtube", "ユーチューブ"],
            "github_discussions": ["github discussions", "github issues"],
        },
        timezone_buckets={
            "jp_evening": (11, 15),  # UTC 11-15 = evening 20-24 JST (UTC+9)
            "na_evening": (0, 6),
            "eu_evening": (18, 22),
        },
    ),
    "kr": RegionProfile(
        "kr",
        "Korea",
        shadow_community={
            "naver_blog": ["naver blog", "네이버 블로그"],
            "velog": ["velog"],
            "disquiet": ["disquiet"],
            "okky": ["okky"],
            "kakao_open_chat": ["오픈채팅", "kakao open chat"],
            "youtube_kr": ["youtube", "유튜브"],
            "github_discussions": ["github discussions", "github issues"],
        },
        timezone_buckets={
            "kr_evening": (11, 15),  # UTC 11-15 = evening 20-24 KST (UTC+9)
            "na_evening": (0, 6),
            "eu_evening": (18, 22),
        },
    ),
    "ru": RegionProfile(
        "ru",
        "Russia / CIS",
        shadow_community={
            "vk": ["vk.com", "вконтакте"],
            "habr": ["habr.com", "хабр"],
            "telegram_channel": ["телеграм канал", "telegram channel"],
            "youtube_ru": ["youtube", "ютуб"],
            "github_discussions": ["github discussions", "github issues"],
        },
        timezone_buckets={
            "moscow_evening": (15, 19),  # UTC 15-19 = evening 18-22 MSK (UTC+3)
            "eu_evening": (18, 22),
            "na_evening": (0, 6),
        },
        regional_providers=frozenset({"yandexgpt"}),
    ),
    "latam": RegionProfile(
        "latam",
        "Latin America",
        shadow_community={
            "reddit_es": ["reddit", r"\br/"],
            "youtube_latam": ["youtube", "youtube tutorial"],
            "discord_latam": ["discord server", "servidor de discord"],
            "whatsapp_group": ["grupo de whatsapp", "whatsapp group"],
            "github_discussions": ["github discussions", "github issues"],
        },
        timezone_buckets={
            "latam_evening": (
                22,
                24,
            ),  # UTC 22-24/0-3 wraps; approximate BRT/ART evening
            "na_evening": (0, 6),
            "eu_evening": (18, 22),
        },
    ),
    "mena": RegionProfile(
        "mena",
        "Middle East / North Africa",
        shadow_community={
            "reddit_arabic": ["reddit", r"\br/"],
            "telegram_channel": ["قناة تيليجرام", "telegram channel"],
            "youtube_arabic": ["youtube", "يوتيوب"],
            "github_discussions": ["github discussions", "github issues"],
        },
        timezone_buckets={
            "gulf_evening": (15, 19),  # UTC 15-19 = evening 18-22 AST/Gulf (UTC+3/+4)
            "eu_evening": (18, 22),
            "na_evening": (0, 6),
        },
    ),
    "global": RegionProfile(
        "global",
        "Global / English-default",
        shadow_community={
            "reddit": ["reddit", r"\br/"],
            "hackernews": ["hacker news", "hn", "y combinator"],
            "discord_server": ["discord server"],
            "youtube": ["youtube", "yt video"],
            "linkedin": ["linkedin"],
            "github_discussions": ["github discussions", "github issues"],
            "producthunt": ["product hunt", "producthunt"],
        },
        timezone_buckets={
            "na_evening": (0, 6),
            "eu_evening": (18, 22),
            "apac_evening": (10, 14),
        },
    ),
}


def get_language_profile(code: str) -> LanguageProfile | None:
    """Return the LanguageProfile for `code`, or None for 'none'/unknown codes."""
    if code in (None, "none", "off"):
        return None
    return LANGUAGE_PROFILES.get(code)


def get_region_profile(code: str) -> RegionProfile:
    """Return the RegionProfile for `code`, defaulting to 'global' if unknown."""
    return REGION_PROFILES.get(code, REGION_PROFILES["global"])
