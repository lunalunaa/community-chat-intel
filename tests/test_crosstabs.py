"""Tests for parallax.core.crosstabs — cross-tabulation logic."""

from datetime import datetime, timezone

from parallax.core import crosstabs as ct
from parallax.core import languages as lang


class TestProviderClusters:
    def test_global_api_cluster(self):
        clusters = ct.build_provider_clusters(lang.get_region_profile("global"))
        assert "global_api" in clusters
        assert "anthropic_claude" in clusters["global_api"]
        assert "openai" in clusters["global_api"]

    def test_regional_api_cluster_cn(self):
        clusters = ct.build_provider_clusters(lang.get_region_profile("cn"))
        assert "regional_api" in clusters
        assert len(clusters["regional_api"]) > 0

    def test_self_hosted_cluster(self):
        clusters = ct.build_provider_clusters(lang.get_region_profile("global"))
        assert "self_hosted" in clusters
        assert "ollama" in clusters["self_hosted"]

    def test_global_region_has_no_regional(self):
        clusters = ct.build_provider_clusters(lang.get_region_profile("global"))
        assert "regional_api" not in clusters or len(clusters["regional_api"]) == 0


class TestMessagingBuckets:
    def test_enterprise_im_bucket(self):
        assert "enterprise_im" in ct.MESSAGING_BUCKETS
        assert "feishu_lark" in ct.MESSAGING_BUCKETS["enterprise_im"]
        assert "slack" in ct.MESSAGING_BUCKETS["enterprise_im"]

    def test_consumer_im_bucket(self):
        assert "consumer_im" in ct.MESSAGING_BUCKETS
        assert "discord" in ct.MESSAGING_BUCKETS["consumer_im"]
        assert "telegram" in ct.MESSAGING_BUCKETS["consumer_im"]

    def test_no_overlap_between_buckets(self):
        ent = ct.MESSAGING_BUCKETS["enterprise_im"]
        con = ct.MESSAGING_BUCKETS["consumer_im"]
        assert ent.isdisjoint(con)


class TestUserMessagingBuckets:
    def test_enterprise_user(self):
        user = {"messaging": {"feishu_lark": 5, "slack": 2}}
        buckets = ct.user_messaging_buckets(user)
        assert "enterprise_im" in buckets

    def test_consumer_user(self):
        user = {"messaging": {"discord": 3, "telegram": 1}}
        buckets = ct.user_messaging_buckets(user)
        assert "consumer_im" in buckets

    def test_no_messaging(self):
        user = {"messaging": {}}
        buckets = ct.user_messaging_buckets(user)
        assert len(buckets) == 0

    def test_multi_platform_user(self):
        user = {"messaging": {"feishu_lark": 5, "discord": 3}}
        buckets = ct.user_messaging_buckets(user)
        assert "enterprise_im" in buckets
        assert "consumer_im" in buckets


class TestUserRetention:
    """Test the retention bucketing logic."""

    def test_active_user(self):
        now = datetime(2026, 7, 1, tzinfo=timezone.utc)
        user = {"last_seen": "2026-06-20T00:00:00+00:00"}
        assert ct.user_retention(user, now) == "active_30d"

    def test_lapsed_30_90(self):
        now = datetime(2026, 7, 1, tzinfo=timezone.utc)
        user = {"last_seen": "2026-05-01T00:00:00+00:00"}
        assert ct.user_retention(user, now) == "lapsed_30_90d"

    def test_lapsed_90_plus(self):
        now = datetime(2026, 7, 1, tzinfo=timezone.utc)
        user = {"last_seen": "2026-01-01T00:00:00+00:00"}
        assert ct.user_retention(user, now) == "lapsed_90d_plus"

    def test_no_last_seen(self):
        now = datetime(2026, 7, 1, tzinfo=timezone.utc)
        user = {}
        assert ct.user_retention(user, now) == "unknown"
