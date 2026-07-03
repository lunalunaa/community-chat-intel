"""Tests for parallax.core.analyze — core pipeline functions."""

from datetime import datetime, timezone


from parallax.core import analyze
from parallax.core import keywords as kw
from parallax.core import languages as lang


class TestHashId:
    def test_consistent_hash(self):
        h1 = analyze._hash_id("user123", "salt")
        h2 = analyze._hash_id("user123", "salt")
        assert h1 == h2

    def test_different_users_different_hash(self):
        h1 = analyze._hash_id("user1", "salt")
        h2 = analyze._hash_id("user2", "salt")
        assert h1 != h2

    def test_different_salt_different_hash(self):
        h1 = analyze._hash_id("user1", "salt1")
        h2 = analyze._hash_id("user1", "salt2")
        assert h1 != h2

    def test_hash_format(self):
        h = analyze._hash_id("user1", "salt")
        # SHA-256 hexdigest[:16] = 16 hex chars, no prefix
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)


class TestExtractUrls:
    def test_extracts_single_url(self):
        urls = analyze.extract_urls("visit https://example.com now")
        assert urls == ["https://example.com"]

    def test_extracts_multiple_urls(self):
        urls = analyze.extract_urls("https://a.com and http://b.com")
        assert len(urls) == 2

    def test_no_urls(self):
        urls = analyze.extract_urls("just plain text")
        assert urls == []


class TestClassifyUrl:
    def test_official_domain(self):
        cat, domain = analyze.classify_url("https://example.com/docs")
        assert cat == "official"
        assert "example.com" in domain

    def test_impersonator_domain(self):
        cat, domain = analyze.classify_url("https://example-product.org.cn")
        assert cat == "impersonator"
        assert "example-product.org.cn" in domain

    def test_huggingface(self):
        cat, domain = analyze.classify_url("https://huggingface.co/model")
        assert cat == "hf"

    def test_regional_vendor(self):
        cat, domain = analyze.classify_url("https://api.deepseek.com/v1")
        assert cat == "regional_vendor"

    def test_messaging_domain(self):
        cat, domain = analyze.classify_url("https://open.feishu.cn/bot")
        assert cat == "messaging"

    def test_other_domain(self):
        cat, domain = analyze.classify_url("https://random-blog.com/post")
        assert cat == "other"

    def test_case_insensitive(self):
        cat, domain = analyze.classify_url("HTTPS://EXAMPLE.COM/Page")
        assert cat == "official"


class TestIsQuestion:
    def test_english_question(self):
        pat = kw.question_pattern_for("en")
        assert analyze.is_question("how do I install this?", pat)

    def test_not_a_question(self):
        pat = kw.question_pattern_for("en")
        assert not analyze.is_question("this is a statement about cats", pat)

    def test_chinese_question(self):
        pat = kw.question_pattern_for("zh")
        assert analyze.is_question("怎么安装？", pat)


class TestClassifyLanguageWrapper:
    def test_none_profile_returns_target_for_nonempty(self):
        assert analyze.classify_language("hello world", None) == "target"

    def test_none_profile_returns_unknown_for_empty(self):
        assert analyze.classify_language("", None) == "unknown"

    def test_none_profile_returns_unknown_for_whitespace(self):
        assert analyze.classify_language("   ", None) == "unknown"

    def test_delegates_to_languages_module(self):
        profile = lang.get_language_profile("zh")
        assert profile is not None
        assert analyze.classify_language("这是中文", profile) == "target"


class TestUserProfileLanguagePrimary:
    def test_silent_user(self):
        u = analyze.UserProfile(
            user_id="u1",
            display_name="test",
            first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc),
            last_seen=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        assert u.language_primary() == "silent"

    def test_target_primary(self):
        u = analyze.UserProfile(
            user_id="u1",
            display_name="test",
            first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc),
            last_seen=datetime(2026, 1, 1, tzinfo=timezone.utc),
            message_count=10,
            target_lang_count=8,
            other_lang_count=2,
        )
        assert u.language_primary() == "target_primary"

    def test_other_primary(self):
        u = analyze.UserProfile(
            user_id="u1",
            display_name="test",
            first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc),
            last_seen=datetime(2026, 1, 1, tzinfo=timezone.utc),
            message_count=10,
            target_lang_count=1,
            other_lang_count=9,
        )
        assert u.language_primary() == "other_primary"

    def test_bilingual(self):
        u = analyze.UserProfile(
            user_id="u1",
            display_name="test",
            first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc),
            last_seen=datetime(2026, 1, 1, tzinfo=timezone.utc),
            message_count=10,
            target_lang_count=4,
            other_lang_count=4,
            mixed_count=2,
        )
        assert u.language_primary() == "bilingual"

    def test_mixed_counts_as_half(self):
        """Mixed messages count as 0.5 toward each side."""
        u = analyze.UserProfile(
            user_id="u1",
            display_name="test",
            first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc),
            last_seen=datetime(2026, 1, 1, tzinfo=timezone.utc),
            message_count=10,
            target_lang_count=3,
            other_lang_count=3,
            mixed_count=4,
        )
        # target_pct = (3 + 0.5*4) / 10 = 0.5 → bilingual
        assert u.language_primary() == "bilingual"


class TestMinMaxTs:
    def test_min_ts_empty_list(self):
        assert analyze._min_ts([]) is None

    def test_max_ts_empty_list(self):
        assert analyze._max_ts([]) is None

    def test_min_ts_single(self):
        m = analyze.Message(
            platform="discord",
            channel="general",
            message_id="1",
            author_id="u1",
            author_name="a",
            content="test",
            timestamp=datetime(2026, 1, 15, tzinfo=timezone.utc),
        )
        assert analyze._min_ts([m]) == "2026-01-15T00:00:00+00:00"

    def test_max_ts_single(self):
        m = analyze.Message(
            platform="discord",
            channel="general",
            message_id="1",
            author_id="u1",
            author_name="a",
            content="test",
            timestamp=datetime(2026, 1, 15, tzinfo=timezone.utc),
        )
        assert analyze._max_ts([m]) == "2026-01-15T00:00:00+00:00"

    def test_min_ts_multiple(self):
        msgs = [
            analyze.Message(
                platform="discord",
                channel="c",
                message_id=str(i),
                author_id="u",
                author_name="a",
                content="t",
                timestamp=datetime(2026, 1, d, tzinfo=timezone.utc),
            )
            for d, i in zip([15, 1, 28], [1, 2, 3])
        ]
        assert analyze._min_ts(msgs) == "2026-01-01T00:00:00+00:00"
        assert analyze._max_ts(msgs) == "2026-01-28T00:00:00+00:00"


class TestEnsureSalt:
    def test_generates_salt(self, tmp_path):
        salt_path = tmp_path / "salt.key"
        salt = analyze.ensure_salt(salt_path)
        assert len(salt) > 0
        assert salt_path.exists()

    def test_reuses_existing_salt(self, tmp_path):
        salt_path = tmp_path / "salt.key"
        salt1 = analyze.ensure_salt(salt_path)
        salt2 = analyze.ensure_salt(salt_path)
        assert salt1 == salt2
