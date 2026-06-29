from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split(".") if part.isdigit())


def test_default_dependency_surface_excludes_security_gated_crawl4ai_chain() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = tuple(pyproject["project"]["dependencies"])

    assert not any(item.startswith("crawl4ai") for item in dependencies)
    assert any(item.startswith("lxml>=6.1.0") for item in dependencies)


def test_lockfile_excludes_unpatched_crawl4ai_and_nltk_and_uses_patched_lxml() -> None:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    versions = {package["name"]: package["version"] for package in lock["package"]}

    assert "crawl4ai" not in versions
    assert "nltk" not in versions
    assert _version_tuple(versions["lxml"]) >= (6, 1, 0)


def test_go_sidecar_uses_patched_x_net_floor() -> None:
    go_mod = (ROOT / "sidecars" / "masa-twitter-scraper" / "go.mod").read_text(
        encoding="utf-8"
    )

    assert "go 1.25.0" in go_mod
    assert "golang.org/x/net v0.56.0" in go_mod
    assert "golang.org/x/net v0.28.0" not in go_mod
