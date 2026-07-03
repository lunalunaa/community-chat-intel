"""Tests for parallax.core.keywords — keyword dictionaries & matching."""

import re


from parallax.core import keywords as kw


class TestCompileDict:
    def test_compiles_ascii_with_word_boundaries(self):
        compiled = kw._compile_dict({"test": ["openai"]})
        assert "test" in compiled
        assert len(compiled["test"]) == 1
        assert isinstance(compiled["test"][0], re.Pattern)

    def test_compiles_cjk_verbatim(self):
        compiled = kw._compile_dict({"test": ["飞书"]})
        assert len(compiled["test"]) == 1

    def test_compiles_pre_escaped_regex(self):
        compiled = kw._compile_dict({"test": [r"\bqq\b"]})
        assert len(compiled["test"]) == 1

    def test_compiles_mixed_entries(self):
        compiled = kw._compile_dict({"test": ["openai", "飞书", r"\buv\b"]})
        assert len(compiled["test"]) == 3

    def test_empty_dict(self):
        compiled = kw._compile_dict({})
        assert compiled == {}


class TestMatchAny:
    def test_matches_single_label(self):
        compiled = kw._compile_dict({"openai": ["openai"], "anthropic": ["claude"]})
        hits = kw.match_any("I use openai for everything", compiled)
        assert hits == ["openai"]

    def test_matches_multiple_labels(self):
        compiled = kw._compile_dict({"openai": ["openai"], "anthropic": ["claude"]})
        hits = kw.match_any("switched from openai to claude", compiled)
        assert set(hits) == {"openai", "anthropic"}

    def test_no_matches(self):
        compiled = kw._compile_dict({"openai": ["openai"]})
        hits = kw.match_any("nothing relevant here", compiled)
        assert hits == []

    def test_cjk_verbatim_match(self):
        compiled = kw._compile_dict({"feishu": ["飞书"]})
        hits = kw.match_any("我想接入飞书机器人", compiled)
        assert "feishu" in hits

    def test_case_insensitive(self):
        compiled = kw._compile_dict({"openai": ["openai"]})
        hits = kw.match_any("I love OpenAI and OPENAI", compiled)
        assert "openai" in hits

    def test_word_boundary_prevents_partial_match(self):
        """'openai' should not match inside 'openaicom'."""
        compiled = kw._compile_dict({"openai": ["openai"]})
        hits = kw.match_any("visit openaicom today", compiled)
        assert "openai" not in hits


class TestCompiledDictionaries:
    """Verify the pre-compiled dictionaries exist and are non-empty."""

    def test_providers_compiled(self):
        assert len(kw.PROVIDERS_COMPILED) > 0
        for label, patterns in kw.PROVIDERS_COMPILED.items():
            assert len(patterns) > 0, f"Provider {label} has no compiled patterns"

    def test_competitors_compiled(self):
        assert len(kw.COMPETITORS_COMPILED) > 0

    def test_messaging_compiled(self):
        assert len(kw.MESSAGING_COMPILED) > 0

    def test_features_compiled(self):
        assert len(kw.PRODUCT_FEATURES_COMPILED) > 0

    def test_friction_compiled(self):
        assert len(kw.FRICTION_COMPILED) > 0

    def test_install_compiled(self):
        assert len(kw.INSTALL_COMPILED) > 0

    def test_acquisition_compiled(self):
        assert len(kw.ACQUISITION_COMPILED) > 0


class TestQuestionPatterns:
    def test_english_question_mark(self):
        pat = kw.question_pattern_for("en")
        assert pat.search("how do I install this?")
        assert pat.search("what is this?")

    def test_english_question_words(self):
        pat = kw.question_pattern_for("en")
        assert pat.search("how do I configure the API")
        assert pat.search("can you help me")

    def test_chinese_question_markers(self):
        pat = kw.question_pattern_for("zh")
        assert pat.search("怎么安装？")
        assert pat.search("如何配置api")

    def test_japanese_question_markers(self):
        pat = kw.question_pattern_for("ja")
        assert pat.search("どうすればいいですか？")

    def test_korean_question_markers(self):
        pat = kw.question_pattern_for("ko")
        assert pat.search("어떻게 사용하나요?")

    def test_fallback_to_english(self):
        """Unknown language code falls back to English-only."""
        pat = kw.question_pattern_for("nonsense")
        assert pat.search("how do I install?")
        # Chinese-only pattern should not match in fallback
        assert not pat.search("怎么安装")

    def test_none_language_falls_back_to_english(self):
        pat = kw.question_pattern_for(None)
        assert pat.search("how do I install?")

    def test_default_pattern_is_english(self):
        assert kw.QUESTION_PATTERN.search("how do I install?")

    def test_combined_pattern_includes_both(self):
        """When a language is specified, both English + target patterns work."""
        pat = kw.question_pattern_for("zh")
        assert pat.search("how do I install?")  # English fallback
        assert pat.search("怎么安装？")  # Chinese


class TestUrlPattern:
    def test_extracts_https(self):
        urls = kw.URL_PATTERN.findall("visit https://example.com today")
        assert "https://example.com" in urls

    def test_extracts_http(self):
        urls = kw.URL_PATTERN.findall("visit http://example.com today")
        assert "http://example.com" in urls

    def test_no_urls_in_plain_text(self):
        urls = kw.URL_PATTERN.findall("no urls here just text")
        assert urls == []

    def test_multiple_urls(self):
        urls = kw.URL_PATTERN.findall("https://a.com and https://b.com")
        assert len(urls) == 2
