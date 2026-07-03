"""Keyword dictionaries for the community chat-history analysis pipeline.

Each dictionary maps a canonical label → a list of pattern strings.
Patterns are matched case-insensitively as whole-word / whole-phrase regex.
Non-ASCII terms (any script — CJK, Cyrillic, Arabic, etc.) match verbatim;
ASCII terms match as word-boundaries.

Used by analyze.py's keyword-extraction stage.

CUSTOMIZE THIS FILE for your own product/community. The sections marked
EXAMPLE below contain placeholder entries to show the pattern shape —
replace them with your own product's actual feature names, competitor
names, and impersonator domains. The generic sections (providers, messaging
platforms, friction signals, install paths, acquisition channels) are
broad enough to work out-of-the-box for most AI-product communities, but
you can extend or trim them to match your ecosystem.
"""

from __future__ import annotations

import re

# ----------------------------------------------------------------------------
# 1. LLM / AI providers — who do users name when they talk about models?
#    Broad coverage of both global and regional providers. Trim or extend
#    to match your community's ecosystem.
# ----------------------------------------------------------------------------
PROVIDERS: dict[str, list[str]] = {
    "openai": ["openai", "chatgpt", "gpt-4", "gpt-5", "codex"],
    "anthropic_claude": ["claude", "anthropic", "sonnet", "opus"],
    "gemini_google": ["gemini", "google ai", "bard"],
    "deepseek": ["deepseek"],
    "qwen_alibaba": ["qwen", "通义", "通义千问", "dashscope", "百炼"],
    "glm_zhipu": ["glm", "智谱", "chatglm", "zhipu", "bigmodel"],
    "kimi_moonshot": ["kimi", "moonshot", "月之暗面"],
    "minimax": ["minimax", "abab"],
    "volcengine_ark": ["volcengine", "火山引擎", "方舟", "ark"],
    "doubao": ["doubao", "豆包"],
    "baichuan": ["baichuan", "百川"],
    "yi_01ai": ["01.ai", "零一万物", "yi-"],
    "yandexgpt": ["yandexgpt", "yandex gpt"],
    # Aggregators and self-host
    "openrouter": ["openrouter", "or-"],
    "huggingface": ["huggingface", "hf", "🤗"],
    "modelscope": ["modelscope", "魔搭"],
    "ollama": ["ollama"],
    "vllm": ["vllm"],
    "llamacpp": ["llama.cpp", "llamacpp", "gguf"],
    "lmstudio": ["lm studio", "lmstudio"],
}

# ----------------------------------------------------------------------------
# 2. Competitors — EXAMPLE category. Replace with your own market's
#    competitor products / slang / nicknames. Left in with placeholder
#    entries to show the pattern (grouping an official name + common
#    aliases + colloquial/slang variants under one canonical label).
# ----------------------------------------------------------------------------
COMPETITORS: dict[str, list[str]] = {
    "competitor_a": ["competitor a", "competitor-a", "competitora"],
    "competitor_b": ["competitor b", "competitor-b", "competitorb"],
    "competitor_c": ["competitor c", "competitor-c", "competitorc"],
}

# ----------------------------------------------------------------------------
# 3. Messaging platforms — where do users want to run agents / bots?
#    Broad coverage of both global and regional platforms.
# ----------------------------------------------------------------------------
MESSAGING: dict[str, list[str]] = {
    "discord": ["discord"],
    "telegram": ["telegram", "tg", "电报"],
    "slack": ["slack"],
    "feishu_lark": ["feishu", "飞书", "lark", "larksuite"],
    "wechat": ["wechat", "微信", "weixin"],
    "wecom": ["wecom", "企业微信", "企微", "wework"],
    "dingtalk": ["dingtalk", "钉钉"],
    "qq": [r"\bqq\b"],
    "signal": ["signal messenger", "signal app"],
    "matrix": ["matrix.org", "matrix protocol", "element.io"],
    "email": ["email", "邮件", "smtp", "imap"],
    "sms": [r"\bsms\b", "短信"],
    "whatsapp": ["whatsapp"],
}

# ----------------------------------------------------------------------------
# 4. Product features — EXAMPLE category (generic AI-agent feature names).
#    Replace with your own product's actual feature/tool names so mentions
#    of them get tagged correctly. The entries below are illustrative of
#    the kind of features an AI-agent product might have.
# ----------------------------------------------------------------------------
PRODUCT_FEATURES: dict[str, list[str]] = {
    "skills": ["skills", "技能", "skill"],
    "memory": ["memory", "记忆", "persistent memory"],
    "cron": ["cron", "cronjob", "定时任务", "scheduled task"],
    "delegate": ["delegate_task", "subagent", "子任务", "委派"],
    "browser": ["browser automation", "浏览器自动化"],
    "vision": ["vision_analyze", "视觉", "image analysis"],
    "tts": ["text_to_speech", "tts", "语音合成"],
    "mcp": ["mcp", "mcp server", "model context protocol"],
    "execute_code": ["execute_code", "exec_code", "python sandbox"],
    "terminal_tool": ["terminal tool", "shell tool", "bash tool"],
    "search": ["search_files", "web_search"],
    "edit": [r"\bpatch\b", "write_file", "read_file", "edit_file"],
}

# ----------------------------------------------------------------------------
# 5. Install / deploy paths
# ----------------------------------------------------------------------------
INSTALL: dict[str, list[str]] = {
    "wsl": ["wsl", "wsl2", "windows subsystem"],
    "docker": ["docker", "docker-compose", "容器"],
    "linux_native": ["ubuntu", "debian", "arch", "fedora", "linux native"],
    "macos": ["macos", "mac os", " osx ", "brew"],
    "windows_native": ["windows native", "win10", "win11"],
    "uv_python": [r"\buv\b", "uv pip", "uv install"],
    "pip_python": [r"\bpip\b", "pip install"],
    "hosted_service": ["hosted service", "managed service", "cloud subscription"],
    "vps_ssh": [r"\bssh\b", "vps", "remote server"],
}

# ----------------------------------------------------------------------------
# 6. Friction signals — errors, failures, help-requests
#    Includes patterns in multiple scripts since friction language varies
#    by community language. Extend with your community's language as needed.
# ----------------------------------------------------------------------------
FRICTION: dict[str, list[str]] = {
    "error_generic": ["error", "exception", "traceback", "报错", "错误", "异常"],
    "timeout": ["timeout", "time out", "超时"],
    "network_blocked": [
        "vpn",
        "proxy",
        "blocked",
        "无法访问",
        "访问不了",
        "region-locked",
    ],
    "slow_network": ["slow", "很慢", "卡", "lag", "网络慢"],
    "failed": ["failed", "failure", "失败"],
    "stuck": ["stuck", "卡住", "hang"],
    "confused": [r"\bhow\b", "怎么", "怎样", "如何", "不会"],
    "help_request": ["help", "求助", "帮忙", "请问"],
    "broken": ["broken", "坏了", "挂了", "doesn't work", "不能用"],
    "oauth_issue": ["oauth", "auth flow", "login fail", "登录失败", "认证"],
    "key_issue": ["api key", "api_key", "密钥", "token invalid", "unauthorized"],
}

# ----------------------------------------------------------------------------
# 7. Impersonator / suspicious domains — EXAMPLE category.
#    Replace with your own product's known impersonator/clone domains.
# ----------------------------------------------------------------------------
IMPERSONATOR_DOMAINS: list[str] = [
    "example-product.org.cn",
    "exampleproductai.cn",
    "exampleproduct.org.cn",
]

# Legitimate domains (for comparison ratio) — EXAMPLE category, replace with
# your own product's real domains.
OFFICIAL_DOMAINS: list[str] = [
    "example.com",
    "docs.example.com",
    "github.com/example-org",
]

# ----------------------------------------------------------------------------
# 8. Acquisition-channel markers — where did users say they found the product?
#    (Shadow-community markers moved to languages.py's REGION_PROFILES since
#    "where else do people hang out" is region-specific, not universal.)
# ----------------------------------------------------------------------------
ACQUISITION: dict[str, list[str]] = {
    "twitter_x": ["twitter", " x.com", "推特"],
    "github_trending": ["github trending", "github 热榜", "star"],
    "hf_model_page": ["huggingface", "hf model", "model card"],
    "friend_recommendation": ["friend", "朋友", "同事", "recommended"],
    "article_link": ["article", "blog post", "博客", "文章"],
    "video": ["video", "视频"],
    "reddit": ["reddit", r"\br/"],
    "hackernews": ["hacker news", "hn", "y combinator"],
}

# ----------------------------------------------------------------------------
# URL extraction
# ----------------------------------------------------------------------------
URL_PATTERN = re.compile(r"https?://[^\s)\]>,'\"]+", re.IGNORECASE)

# ----------------------------------------------------------------------------
# Question detection — per-language heuristics. English is always checked;
# add an entry here (keyed by the same language code used in languages.py)
# for additional target-language question markers. Unknown language codes
# fall back to English-only detection.
# ----------------------------------------------------------------------------
QUESTION_PATTERN_EN = re.compile(
    r"[?]\s*$|\b(how|what|when|where|why|which|who|is it|can i|can you|does|do i|should i)\b",
    re.IGNORECASE,
)

QUESTION_PATTERNS_BY_LANGUAGE: dict[str, re.Pattern] = {
    "zh": re.compile(
        r"[？?]\s*$|怎么|怎样|如何|什么|为什么|可以吗|能不能|吗\s*[？?]?\s*$|呢\s*[？?]?\s*$"
    ),
    "ja": re.compile(r"[？?]\s*$|どう|なぜ|何|ですか\s*[？?]?\s*$|ますか\s*[？?]?\s*$"),
    "ko": re.compile(r"[？?]\s*$|어떻게|왜|무엇|인가요\s*[？?]?\s*$|나요\s*[？?]?\s*$"),
    "ru": re.compile(r"[?]\s*$|как\b|почему\b|что\b|где\b|можно ли\b", re.IGNORECASE),
    "es": re.compile(
        r"[?¿]\s*$|\bcómo\b|\bqué\b|\bpor qué\b|\bcuándo\b|\bdónde\b", re.IGNORECASE
    ),
    "fr": re.compile(
        r"[?]\s*$|\bcomment\b|\bpourquoi\b|\bquoi\b|\bquand\b|\boù\b", re.IGNORECASE
    ),
    "de": re.compile(
        r"[?]\s*$|\bwie\b|\bwarum\b|\bwas\b|\bwann\b|\bwo\b", re.IGNORECASE
    ),
    "pt": re.compile(
        r"[?]\s*$|\bcomo\b|\bpor que\b|\bquando\b|\bonde\b", re.IGNORECASE
    ),
    "ar": re.compile(r"[؟?]\s*$|كيف|لماذا|ماذا|متى|أين"),
}


def question_pattern_for(language_code: str | None) -> re.Pattern:
    """Return the compiled question-detection pattern for a target language.

    Always includes the English pattern (most communities code-switch into
    English for technical terms). Falls back to English-only when the
    language code has no dedicated pattern registered above.
    """
    lang_pat = QUESTION_PATTERNS_BY_LANGUAGE.get(language_code or "")
    if lang_pat is None:
        return QUESTION_PATTERN_EN
    combined = f"(?:{QUESTION_PATTERN_EN.pattern})|(?:{lang_pat.pattern})"
    return re.compile(combined, re.IGNORECASE)


# Default question pattern (English-only) for callers that don't pass
# a language code.
QUESTION_PATTERN = QUESTION_PATTERN_EN


# ----------------------------------------------------------------------------
# Compile helpers
# ----------------------------------------------------------------------------
def _compile_dict(d: dict[str, list[str]]) -> dict[str, list[re.Pattern]]:
    """Compile each pattern list into regex. Handles both non-ASCII verbatim
    and ASCII word-boundaried patterns."""
    compiled: dict[str, list[re.Pattern]] = {}
    for label, patterns in d.items():
        compiled_patterns = []
        for p in patterns:
            if p.startswith(r"\b") or p.startswith(r"("):
                # already a regex
                compiled_patterns.append(re.compile(p, re.IGNORECASE))
            elif re.search(r"[^\x00-\x7f]", p):
                # non-ASCII (any script) — verbatim substring match, no word boundaries
                compiled_patterns.append(re.compile(re.escape(p), re.IGNORECASE))
            else:
                # ASCII — word boundary
                compiled_patterns.append(
                    re.compile(rf"(?<!\w){re.escape(p)}(?!\w)", re.IGNORECASE)
                )
        compiled[label] = compiled_patterns
    return compiled


# Public alias — languages.py's REGION_PROFILES.shadow_community dicts use
# this same compile helper (kept public rather than importing a private name).
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
