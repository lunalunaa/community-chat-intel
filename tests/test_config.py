"""Tests for parallax.core.config — config file loading."""

from parallax.core import config


class TestLoadFactSchema:
    def test_loads_successfully(self):
        schema = config.load_fact_schema()
        assert "categories" in schema
        assert "prompt_intro" in schema
        assert "prompt_rules" in schema
        assert isinstance(schema["categories"], list)
        assert len(schema["categories"]) > 0

    def test_categories_have_fields(self):
        schema = config.load_fact_schema()
        for cat in schema["categories"]:
            assert "field" in cat
            assert "fields" in cat
            assert isinstance(cat["fields"], dict)

    def test_known_categories_present(self):
        schema = config.load_fact_schema()
        fields = [c["field"] for c in schema["categories"]]
        assert "install_problems" in fields
        assert "provider_usage" in fields
        assert "competitor_mentions" in fields


class TestLoadQueries:
    def test_loads_successfully(self):
        queries = config.load_queries()
        assert "zh" in queries
        assert "en" in queries
        assert isinstance(queries["zh"], dict)
        assert len(queries["zh"]) > 0

    def test_zh_has_known_query(self):
        queries = config.load_queries()
        assert "install_friction" in queries["zh"]

    def test_en_has_known_query(self):
        queries = config.load_queries()
        assert "install_friction" in queries["en"]


class TestLoadBrandPatterns:
    def test_loads_successfully(self):
        patterns = config.load_brand_patterns()
        assert isinstance(patterns, dict)
        assert len(patterns) > 0

    def test_has_known_pattern(self):
        patterns = config.load_brand_patterns()
        assert "product_official" in patterns
        assert "competitor_b" in patterns


class TestLoadUrlDomains:
    def test_loads_successfully(self):
        domains = config.load_url_domains()
        assert isinstance(domains, dict)
        assert len(domains) > 0

    def test_has_regional_vendor(self):
        domains = config.load_url_domains()
        assert "regional_vendor" in domains
        assert isinstance(domains["regional_vendor"], list)
        assert "deepseek.com" in domains["regional_vendor"]

    def test_has_messaging(self):
        domains = config.load_url_domains()
        assert "messaging" in domains
        assert "feishu.cn" in domains["messaging"]


class TestBuildExtractionPrompt:
    def test_prompt_contains_json_schema(self):
        schema = config.load_fact_schema()
        prompt = config.build_extraction_prompt(schema, "English")
        assert "{" in prompt
        assert "}" in prompt
        assert "install_problems" in prompt

    def test_prompt_contains_language_name(self):
        schema = config.load_fact_schema()
        prompt = config.build_extraction_prompt(schema, "Japanese")
        assert "Japanese" in prompt

    def test_prompt_contains_rules(self):
        schema = config.load_fact_schema()
        prompt = config.build_extraction_prompt(schema, "English")
        assert "Rules:" in prompt

    def test_prompt_ends_with_messages_marker(self):
        schema = config.load_fact_schema()
        prompt = config.build_extraction_prompt(schema, "English")
        assert prompt.rstrip().endswith("MESSAGES:")


class TestGetExtractionCategories:
    def test_returns_list_of_strings(self):
        schema = config.load_fact_schema()
        cats = config.get_extraction_categories(schema)
        assert isinstance(cats, list)
        assert all(isinstance(c, str) for c in cats)

    def test_includes_known_categories(self):
        schema = config.load_fact_schema()
        cats = config.get_extraction_categories(schema)
        assert "install_problems" in cats
        assert "competitor_mentions" in cats
