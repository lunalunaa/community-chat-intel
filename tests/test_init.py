"""Tests for parallax.core.init — project scaffolding."""

from parallax.core.init import init_project


class TestInitProject:
    def test_creates_directory_structure(self, tmp_path):
        project = tmp_path / "my-project"
        init_project(str(project), platform="discord", language="zh", region="cn")

        assert project.exists()
        assert (project / "config").is_dir()
        assert (project / "data").is_dir()
        assert (project / "out").is_dir()
        assert (project / "user_hash_salt.key").exists()
        assert (project / ".gitignore").exists()
        assert (project / "README.md").exists()

    def test_copies_config_files(self, tmp_path):
        project = tmp_path / "test"
        init_project(str(project))

        config_dir = project / "config"
        yaml_files = list(config_dir.glob("*.yaml"))
        json_files = list(config_dir.glob("*.json"))
        assert len(yaml_files) >= 4  # fact_schema, queries, brand_patterns, url_domains
        assert len(json_files) >= 1  # canonical_schema.json

    def test_salt_file_has_content(self, tmp_path):
        project = tmp_path / "test"
        init_project(str(project))

        salt = (project / "user_hash_salt.key").read_text()
        assert len(salt.strip()) > 0
        assert len(salt.strip()) == 64  # token_hex(32) = 64 hex chars

    def test_gitignore_covers_secrets_and_data(self, tmp_path):
        project = tmp_path / "test"
        init_project(str(project))

        gi = (project / ".gitignore").read_text()
        assert "*.key" in gi
        assert "data/*" in gi
        assert "out/*" in gi

    def test_readme_contains_platform(self, tmp_path):
        project = tmp_path / "test"
        init_project(str(project), platform="slack", language="en", region="global")

        readme = (project / "README.md").read_text()
        assert "--platform slack" in readme
        assert "--target-language en" in readme
        assert "--region global" in readme

    def test_readme_contains_incremental_section(self, tmp_path):
        project = tmp_path / "test"
        init_project(str(project))

        readme = (project / "README.md").read_text()
        assert "--incremental" in readme

    def test_fails_on_existing_directory(self, tmp_path):
        project = tmp_path / "existing"
        project.mkdir()
        (project / "file.txt").write_text("hello")

        import pytest

        with pytest.raises(SystemExit):
            init_project(str(project))

    def test_data_and_out_have_gitkeep(self, tmp_path):
        project = tmp_path / "test"
        init_project(str(project))

        assert (project / "data" / ".gitkeep").exists()
        assert (project / "out" / ".gitkeep").exists()
