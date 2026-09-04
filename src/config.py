"""Single loader for config.md — every module in src/ and app.py must read
parameters through this module. Nothing here should be duplicated or
hardcoded elsewhere: to change departments, thresholds, or paths, edit
config.md only.

config.md is a human-readable Markdown file that embeds one machine-readable
```yaml fenced block. This loader extracts and parses that block.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_MD_PATH = PROJECT_ROOT / "config.md"

_YAML_BLOCK_RE = re.compile(r"```yaml\s*\n(.*?)```", re.DOTALL)


def _extract_yaml_block(md_text: str) -> dict[str, Any]:
    match = _YAML_BLOCK_RE.search(md_text)
    if not match:
        raise ValueError(
            f"No fenced ```yaml block found in {CONFIG_MD_PATH}. "
            "config.md must contain exactly one such block."
        )
    return yaml.safe_load(match.group(1))


@dataclass(frozen=True)
class Department:
    name: str
    ubigeo_dep: str
    region_type: str


@dataclass(frozen=True)
class Config:
    raw: dict[str, Any] = field(repr=False)

    @property
    def departments(self) -> list[Department]:
        return [Department(**d) for d in self.raw["departments"]]

    @property
    def department_names(self) -> list[str]:
        return [d.name for d in self.departments]

    def path(self, key: str) -> Path:
        """Resolve a paths.<key> entry from config.md to an absolute Path,
        creating the directory if it does not exist."""
        rel = self.raw["paths"][key]
        p = PROJECT_ROOT / rel
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def resolutive_categories(self) -> list[str]:
        return list(self.raw["resolutive_categories"])

    @property
    def non_resolutive_categories(self) -> list[str]:
        return list(self.raw["non_resolutive_categories"])

    @property
    def active_status_values(self) -> list[str]:
        return list(self.raw["active_status_values"])

    @property
    def peru_bbox(self) -> dict[str, float]:
        return dict(self.raw["validation"]["peru_bbox"])

    @property
    def routing(self) -> dict[str, Any]:
        return dict(self.raw["routing"])

    @property
    def metrics(self) -> dict[str, Any]:
        return dict(self.raw["metrics"])

    @property
    def dashboard(self) -> dict[str, Any]:
        return dict(self.raw["dashboard"])

    @property
    def sources(self) -> dict[str, Any]:
        return dict(self.raw["sources"])

    @property
    def random_seed(self) -> int:
        return int(self.raw["project"]["random_seed"])


def load_config() -> Config:
    text = CONFIG_MD_PATH.read_text(encoding="utf-8")
    return Config(raw=_extract_yaml_block(text))


if __name__ == "__main__":
    cfg = load_config()
    print("Departamentos:", cfg.department_names)
    print("Categorías resolutivas:", cfg.resolutive_categories)
    print("Engine de ruteo:", cfg.routing["engine"])
    print("raw_dir ->", cfg.path("raw_dir"))
