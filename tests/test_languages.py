"""Tests for parallax.core.languages — language & region profiles."""

import re


from parallax.core import languages as lang


class TestLanguageProfiles:
    """Verify all registered language profiles have valid configuration."""

    def test_all_profiles_have_codes(self):
        for code, profile in lang.LANGUAGE_PROFILES.items():
            assert profile.code == code, (
                f"Profile code mismatch: {code} vs {profile.code}"
            )

    def test_all_profiles_have_names(self):
        for code, profile in lang.LANGUAGE_PROFILES.items():
            assert profile.name, f"Profile {code} has empty name"

    def test_all_profiles_have_threshold(self):
        for code, profile in lang.LANGUAGE_PROFILES.items():
            assert 0 < profile.threshold <= 1, (
                f"Profile {code} has invalid threshold {profile.threshold}"
            )

    def test_script_profiles_have_compiled_pattern(self):
        for code, profile in lang.LANGUAGE_PROFILES.items():
            if profile.script_ranges is not None:
                assert profile.script_pattern is not None, (
                    f"Profile {code} has script_ranges but no compiled pattern"
                )
                assert isinstance(profile.script_pattern, re.Pattern)

    def test_stopword_profiles_have_stopwords(self):
        for code, profile in lang.LANGUAGE_PROFILES.items():
            if profile.script_ranges is None:
                assert len(profile.stopwords) > 0, (
                    f"Profile {code} has no script_ranges and no stopwords"
                )


class TestScriptRatio:
    """Test script-ratio detection for CJK/Cyrillic/Arabic/etc."""

    def test_pure_chinese(self):
        profile = lang.get_language_profile("zh")
        assert profile is not None
        ratio = lang.script_ratio("这是一个纯中文消息", profile)
        assert ratio > 0.7

    def test_pure_english(self):
        profile = lang.get_language_profile("zh")
        assert profile is not None
        ratio = lang.script_ratio("this is a pure english message", profile)
        assert ratio < 0.1

    def test_mixed_chinese_english(self):
        profile = lang.get_language_profile("zh")
        assert profile is not None
        ratio = lang.script_ratio("I think 这个 deepseek 挺好用的", profile)
        assert 0.1 < ratio < 0.7

    def test_japanese_detection(self):
        profile = lang.get_language_profile("ja")
        assert profile is not None
        ratio = lang.script_ratio("これは日本語のメッセージです", profile)
        assert ratio > 0.3

    def test_korean_detection(self):
        profile = lang.get_language_profile("ko")
        assert profile is not None
        ratio = lang.script_ratio("이것은 한국어 메시지입니다", profile)
        assert ratio > 0.3

    def test_russian_detection(self):
        profile = lang.get_language_profile("ru")
        assert profile is not None
        ratio = lang.script_ratio("Это сообщение на русском языке", profile)
        assert ratio > 0.3

    def test_arabic_detection(self):
        profile = lang.get_language_profile("ar")
        assert profile is not None
        ratio = lang.script_ratio("هذه رسالة باللغة العربية", profile)
        assert ratio > 0.3

    def test_empty_string(self):
        profile = lang.get_language_profile("zh")
        assert profile is not None
        assert lang.script_ratio("", profile) == 0.0

    def test_whitespace_only(self):
        profile = lang.get_language_profile("zh")
        assert profile is not None
        assert lang.script_ratio("   \n\t  ", profile) == 0.0

    def test_stopword_profile_uses_stopwords(self):
        """Latin-script profiles (es, fr, de, etc.) use stopword ratio."""
        profile = lang.get_language_profile("es")
        assert profile is not None
        assert profile.script_pattern is None
        ratio = lang.script_ratio("hola como estas el la los", profile)
        assert ratio > 0.3  # several Spanish stopwords


class TestClassifyLanguage:
    """Test the three-tier classification: target / mixed / other / unknown."""

    def test_pure_target_language(self):
        profile = lang.get_language_profile("zh")
        assert profile is not None
        assert lang.classify_language("这是一个纯中文消息", profile) == "target"

    def test_pure_other_language(self):
        profile = lang.get_language_profile("zh")
        assert profile is not None
        assert (
            lang.classify_language("this is a pure english message about cats", profile)
            == "other"
        )

    def test_mixed_language(self):
        profile = lang.get_language_profile("zh")
        assert profile is not None
        result = lang.classify_language("I think 这个 deepseek 挺好用的 maybe", profile)
        assert result in ("mixed", "target")

    def test_empty_string_is_unknown(self):
        profile = lang.get_language_profile("zh")
        assert profile is not None
        assert lang.classify_language("", profile) == "unknown"

    def test_whitespace_is_unknown(self):
        profile = lang.get_language_profile("zh")
        assert profile is not None
        assert lang.classify_language("   ", profile) == "unknown"

    def test_short_target_message(self):
        """Very short target-language messages should still classify."""
        profile = lang.get_language_profile("zh")
        assert profile is not None
        assert lang.classify_language("你好", profile) in ("target", "mixed")

    def test_code_switching_with_enough_hits(self):
        """Messages with ≥3 target-script chars in a ≥20-char message classify as mixed."""
        profile = lang.get_language_profile("zh")
        assert profile is not None
        text = "I am using 这个工具 for my project"
        result = lang.classify_language(text, profile)
        assert result == "mixed"


class TestRegionProfiles:
    """Verify region profiles."""

    def test_all_regions_have_codes(self):
        for code, profile in lang.REGION_PROFILES.items():
            assert profile.code == code

    def test_all_regions_have_shadow_community(self):
        for code, profile in lang.REGION_PROFILES.items():
            assert len(profile.shadow_community) > 0, (
                f"Region {code} has no shadow communities"
            )

    def test_all_regions_have_timezone_buckets(self):
        for code, profile in lang.REGION_PROFILES.items():
            assert len(profile.timezone_buckets) > 0, (
                f"Region {code} has no timezone buckets"
            )

    def test_cn_has_zhihu(self):
        cn = lang.get_region_profile("cn")
        assert cn is not None
        assert "zhihu" in cn.shadow_community

    def test_global_has_reddit(self):
        g = lang.get_region_profile("global")
        assert g is not None
        assert "reddit" in g.shadow_community


class TestGetProfiles:
    def test_get_language_profile_valid(self):
        assert lang.get_language_profile("zh") is not None
        assert lang.get_language_profile("ja") is not None

    def test_get_language_profile_invalid(self):
        assert lang.get_language_profile("nonsense") is None

    def test_get_language_profile_none(self):
        result = lang.get_language_profile(None)  # type: ignore[arg-type]
        assert result is None

    def test_get_language_profile_off(self):
        assert lang.get_language_profile("none") is None
        assert lang.get_language_profile("off") is None

    def test_get_region_profile_valid(self):
        assert lang.get_region_profile("cn") is not None
        assert lang.get_region_profile("global") is not None

    def test_get_region_profile_invalid(self):
        # get_region_profile defaults to 'global' for unknown codes
        result = lang.get_region_profile("nonsense")
        assert result is not None
        assert result.code == "global"
