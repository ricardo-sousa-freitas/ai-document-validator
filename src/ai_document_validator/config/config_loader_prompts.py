"""Load invoice extraction prompts from package configuration."""

from pathlib import Path
from typing import Any, NamedTuple

import yaml


class PromptsConfig(NamedTuple):
    """Prompt templates for structured invoice extraction."""

    system_prompt: str
    extraction_prompt: str


class ConfigLoaderPrompts:
    """Load validated prompt templates for the LLM fallback."""

    def __init__(self, config_path: str | Path | None = None) -> None:
        """Load prompts from the default or supplied YAML path."""
        self.config_path = Path(config_path) if config_path else Path(__file__).with_name("prompts.yaml")
        self._prompts = self._load_config()

    @property
    def prompts(self) -> PromptsConfig:
        """Return loaded prompt templates."""
        return self._prompts

    def _load_config(self) -> PromptsConfig:
        """Read required prompt values from YAML."""
        try:
            with self.config_path.open(encoding="utf-8") as file_handle:
                data: dict[str, Any] = yaml.safe_load(file_handle) or {}
            return PromptsConfig(
                system_prompt=str(data["system_prompt"]),
                extraction_prompt=str(data["extraction_prompt"]),
            )
        except (FileNotFoundError, KeyError, PermissionError, yaml.YAMLError) as exc:
            raise RuntimeError("Unable to load LLM extraction prompts") from exc
