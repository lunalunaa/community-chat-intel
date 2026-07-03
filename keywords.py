"""Keyword dictionaries for the Nous Chinese chat-history analysis pipeline.

Each dictionary maps a canonical label → a list of pattern strings.
Patterns are matched case-insensitively as whole-word / whole-phrase regex.
CJK terms match verbatim; ASCII terms match as word-boundaries.

Used by analyze.py's keyword-extraction stage.
"""

from __future__ import annotations
import re

# ----------------------------------------------------------------------------
# 1. Model providers — who do Chinese users name when they talk about LLMs?
# ----------------------------------------------------------------------------
PROVIDERS: dict[str, list[str]] = {
    # Chinese providers
    "deepseek": ["deepseek", "深度求索", "深度寻索"],
    "kimi_moonshot": ["kimi", "moonshot", "月之暗面", "月暗"],
    "kimi_cn": ["kimi-coding-cn", "kimi.cn", "kimi中国版", "moonshot-cn"],
    "qwen_alibaba": ["qwen", "通义", "通义千问", "dashscope", "百炼", "bailian"],
    "glm_zhipu": ["glm", "智谱", "chatglm", "zhipu", "bigmodel"],
    "minimax": ["minimax", "混元", "abab"],
    "minimax_cn": ["minimax-cn", "minimaxi.com/cn"],
    "volcengine_ark": ["volcengine", "火山引擎", "火山方舟", "方舟", "ark", "arkclaw"],
    "doubao": ["doubao", "豆包"],
    "xiaomi_mimo": ["mimo", "xiaomi-mimo", "小米mimo"],
    "baichuan": ["baichuan", "百川"],
    "yi_01ai": ["01.ai", "零一万物", "yi-"],
    # Western providers
    "anthropic_claude": ["claude", "anthropic", "sonnet", "opus"],
    "openai": ["openai", "chatgpt", "gpt-4", "gpt-5", "codex"],
    "gemini_google": ["gemini", "google ai", "bard"],
    # Aggregators and self-host
    "openrouter": ["openrouter", "or-"],
    "huggingface": ["huggingface", "hf", "🤗", "抱抱脸"],
    "modelscope": ["modelscope", "魔搭"],
    "ollama": ["ollama"],
    "vllm": ["vllm"],
    "llamacpp": ["llama.cpp", "llamacpp", "gguf"],
    "lmstudio": ["lm studio", "lmstudio"],
    # Nous / Hermes
    "nous_hermes": ["nous", "hermes", "nousresearch"],
}

# ----------------------------------------------------------------------------
# 2. Claw products — the 百虾大战 landscape
# ----------------------------------------------------------------------------
CLAWS: dict[str, list[str]] = {
    "openclaw_upstream": ["openclaw", "clawdbot", "open claw"],
    "claw_meme": ["龙虾", "养虾", "养龙虾", "百虾大战"],
    "arkclaw": ["arkclaw", "ark claw", "云虾"],
    "workbuddy": ["workbuddy", "work buddy", "codebuddy"],
    "qclaw": ["qclaw", "q claw"],
    "autoclaw": ["autoclaw", "auto claw", "autoglm"],
    "kimi_claw": ["kimi claw", "kimiclaw"],
    "maxclaw": ["maxclaw", "max claw"],
    "copaw": ["copaw", "co paw", "agentscope"],
    "lobsterai": ["lobsterai", "lobster ai", "有道龙虾"],
    "countbot": ["countbot", "count bot"],
    "duclaw": ["duclaw", "du claw"],
    "dingding_wukong": ["钉钉悟空", "dingding wukong"],
    "qoderwork": ["qoderwork", "qoder work"],
    "miclaw": ["miclaw", "mi claw"],
    "stepclaw": ["stepclaw", "step claw"],
    "coze": ["coze", "扣子", "clawhub"],
}

# ----------------------------------------------------------------------------
# 3. Messaging platforms — where do users want to run agents?
# ----------------------------------------------------------------------------
MESSAGING: dict[str, list[str]] = {
    "feishu": ["feishu", "飞书"],
    "lark_intl": ["lark", "larksuite", "lark international"],
    "wechat": ["wechat", "微信", "wexin", "weixin"],
    "wecom": ["wecom", "企业微信", "企微", "wework"],
    "dingtalk": ["dingtalk", "钉钉", "dingding"],
    "qq": [r"\bqq\b", "腾讯qq"],
    "discord": ["discord"],
    "telegram": ["telegram", "tg", "电报"],
    "slack": ["slack"],
    "signal": ["signal messenger", "signal app"],
    "matrix": ["matrix.org", "matrix protocol", "element.io"],
    "email": ["email", "邮件", "smtp", "imap"],
    "sms": [r"\bsms\b", "短信"],
    "whatsapp": ["whatsapp"],
}

# ----------------------------------------------------------------------------
# 4. Hermes Agent features — what do users actually use?
# ----------------------------------------------------------------------------
HERMES_FEATURES: dict[str, list[str]] = {
    "skills": ["skill_manage", "skill_view", "skills_list", "skills", "技能", "skill"],
    "memory": ["memory", "记忆", "持久化", "persistent memory"],
    "cron": ["cron", "cronjob", "定时任务", "scheduled task"],
    "delegate": ["delegate_task", "subagent", "子任务", "委派"],
    "browser": ["browser_navigate", "browser_click", "browser automation", "浏览器自动化"],
    "vision": ["vision_analyze", "视觉", "image analysis"],
    "tts": ["text_to_speech", "tts", "语音合成"],
    "mcp": ["mcp", "mcp server", "model context protocol"],
    "execute_code": ["execute_code", "exec_code", "python sandbox"],
    "terminal_tool": ["terminal tool", "shell tool", "bash tool"],
    "search": ["search_files", "session_search", "web_search"],
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
    "nous_portal": ["nous portal", "portal subscription", "portal oauth"],
    "vps_ssh": [r"\bssh\b", "vps", "remote server"],
}

# ----------------------------------------------------------------------------
# 6. Friction signals — errors, failures, help-requests
# ----------------------------------------------------------------------------
FRICTION: dict[str, list[str]] = {
    "error_generic": ["error", "exception", "traceback", "报错", "错误", "异常"],
    "timeout": ["timeout", "time out", "超时"],
    "vpn_blocked": ["vpn", "翻墙", "proxy", "blocked", "无法访问", "访问不了"],
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
# 7. Impersonator / suspicious Chinese domains
# ----------------------------------------------------------------------------
IMPERSONATOR_DOMAINS: list[str] = [
    "hermes-agent.org.cn",
    "hermesagentai.cn",
    "hermesagent.org.cn",
    "toolin.ai/blog/hermes-agent",
]

# Legitimate Nous domains (for comparison ratio)
OFFICIAL_DOMAINS: list[str] = [
    "nousresearch.com",
    "hermes-agent.nousresearch.com",
    "github.com/NousResearch",
    "github.com/nous-research",
    "huggingface.co/NousResearch",
]

# ----------------------------------------------------------------------------
# 8. Shadow-community markers — where else do users hang out?
# ----------------------------------------------------------------------------
SHADOW_COMMUNITY: dict[str, list[str]] = {
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
}

# ----------------------------------------------------------------------------
# 9. Acquisition-channel markers — where did users say they found Hermes?
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
# 10. Language detection — CJK ratio threshold
# ----------------------------------------------------------------------------
CJK_PATTERN = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
# default: a message is "Chinese" if ≥30% of non-whitespace chars are CJK
DEFAULT_CJK_THRESHOLD = 0.30

# ----------------------------------------------------------------------------
# URL extraction
# ----------------------------------------------------------------------------
URL_PATTERN = re.compile(r"https?://[^\s)\]>,'\"]+", re.IGNORECASE)

# ----------------------------------------------------------------------------
# Question detection — simple first-pass heuristic
# ----------------------------------------------------------------------------
QUESTION_PATTERN = re.compile(
    r"[?？]\s*$|"
    r"\b(how|what|when|where|why|which|who|is it|can i|can you|does|do i|should i)\b|"
    r"(怎么|怎样|如何|什么|为什么|可以吗|能不能|吗\s*[？?]?\s*$|呢\s*[？?]?\s*$)",
    re.IGNORECASE,
)

# ----------------------------------------------------------------------------
# Compile helpers
# ----------------------------------------------------------------------------
def _compile_dict(d: dict[str, list[str]]) -> dict[str, list[re.Pattern]]:
    """Compile each pattern list into regex. Handles both CJK verbatim and
    ASCII word-boundaried patterns."""
    compiled: dict[str, list[re.Pattern]] = {}
    for label, patterns in d.items():
        compiled_patterns = []
        for p in patterns:
            if p.startswith(r"\b") or p.startswith(r"("):
                # already a regex
                compiled_patterns.append(re.compile(p, re.IGNORECASE))
            elif CJK_PATTERN.search(p):
                # CJK — verbatim substring match, no word boundaries
                compiled_patterns.append(re.compile(re.escape(p), re.IGNORECASE))
            else:
                # ASCII — word boundary
                compiled_patterns.append(re.compile(rf"(?<!\w){re.escape(p)}(?!\w)", re.IGNORECASE))
        compiled[label] = compiled_patterns
    return compiled


PROVIDERS_COMPILED = _compile_dict(PROVIDERS)
CLAWS_COMPILED = _compile_dict(CLAWS)
MESSAGING_COMPILED = _compile_dict(MESSAGING)
HERMES_FEATURES_COMPILED = _compile_dict(HERMES_FEATURES)
INSTALL_COMPILED = _compile_dict(INSTALL)
FRICTION_COMPILED = _compile_dict(FRICTION)
SHADOW_COMMUNITY_COMPILED = _compile_dict(SHADOW_COMMUNITY)
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


def cjk_ratio(text: str) -> float:
    """Fraction of non-whitespace chars that are CJK."""
    stripped = "".join(text.split())
    if not stripped:
        return 0.0
    cjk = sum(1 for c in stripped if CJK_PATTERN.match(c))
    return cjk / len(stripped)
