"""kc.toml defaults and parsing."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from kc.errors import KcError

DEFAULT_CONFIG = """schema_version = "kc.config.v1"
project_id = "kc-project"
data_dir = "knowledge"
state_dir = ".kc"

[output]
default_format = "json"
human_format = "table"
llm_env_var = "LLM"

[source_policy]
copy_sources = false
require_fingerprint = true
require_locator = true
allow_unregistered_citations = false

[citation_policy]
required_for_material_claims = true
citation_token_pattern = "kc_v1"
fail_on_stale_source_fingerprint = true

[index]
fts_enabled = true
semantic_enabled = false
hybrid_enabled = false
rrf_k = 60

[index.semantic]
provider = "model2vec"
model = "potion-base-8M"
dimension = 256
checksum = "sha256:aef1c5e1fd70060804f5295ec8e9ab3ed62e50e79b208435fb77e15c5bf94bb8"
purpose = "ranking_only"

[mutation]
default_dry_run = true
require_yes_for_apply = true
atomic_writes = true
create_snapshots = true
require_idempotency_key_for_apply = false
update_log = true
allow_skip_validate_in_llm = false

[task]
enable_wait_exit_code = true
waiting_exit_code = 40
"""


@dataclass(frozen=True)
class KcConfig:
    schema_version: str = "kc.config.v1"
    project_id: str = "kc-project"
    data_dir: str = "knowledge"
    state_dir: str = ".kc"
    raw: dict | None = None

    @property
    def fail_on_stale_source_fingerprint(self) -> bool:
        return bool(
            (self.raw or {})
            .get("citation_policy", {})
            .get("fail_on_stale_source_fingerprint", True)
        )

    @property
    def update_log(self) -> bool:
        return bool((self.raw or {}).get("mutation", {}).get("update_log", True))

    @property
    def allow_skip_validate_in_llm(self) -> bool:
        return bool((self.raw or {}).get("mutation", {}).get("allow_skip_validate_in_llm", False))

    @property
    def waiting_exit_code(self) -> int:
        return int((self.raw or {}).get("task", {}).get("waiting_exit_code", 40))

    @property
    def semantic_enabled(self) -> bool:
        return bool((self.raw or {}).get("index", {}).get("semantic_enabled", False))

    @property
    def hybrid_enabled(self) -> bool:
        return bool((self.raw or {}).get("index", {}).get("hybrid_enabled", False))

    @property
    def rrf_k(self) -> int:
        return int((self.raw or {}).get("index", {}).get("rrf_k", 60))


def load_config(root: Path | None = None, *, required: bool = False) -> KcConfig:
    root = root or Path.cwd()
    path = root / "kc.toml"
    if not path.exists():
        if required:
            raise KcError(
                code="KC_CONFIG_NOT_FOUND",
                message="kc.toml not found. Run kc init --yes first.",
                details={"path": str(path)},
            )
        return KcConfig(raw={})
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise KcError(
            code="KC_CONFIG_INVALID",
            message=f"Invalid kc.toml: {exc}",
            details={"path": str(path)},
        ) from exc
    return KcConfig(
        schema_version=str(data.get("schema_version", "kc.config.v1")),
        project_id=str(data.get("project_id", "kc-project")),
        data_dir=str(data.get("data_dir", "knowledge")),
        state_dir=str(data.get("state_dir", ".kc")),
        raw=data,
    )
