"""Runtime settings, read once from the environment.

All AWS resource names hang off the stage name, so ``dev``, ``demo`` and ``prod`` can live
side by side and no name is typed in two places. This module never calls AWS, it only works
out which resources and models everything else uses.

Empty env vars count as unset, so ``QLOO_API_KEY=`` in ``.env`` means "no key here" rather
than a key that is empty.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass

STAGE_RE = re.compile(r"^[a-z][a-z0-9-]{1,19}$")
"""Kept short and lowercase because resource names are built from it."""

DEFAULT_REGION = "ap-southeast-2"
"""Sydney: every service Groundtime uses is offered there, Nova on Bedrock included."""

DEFAULT_QLOO_URL = "https://hackathon.api.qloo.com"

DEFAULT_CONCIERGE_MODEL = "global.amazon.nova-2-lite-v1:0"
"""Amazon Nova 2 Lite through Bedrock's global cross-region profile (it has no in-region
endpoint). Any Converse model with tool calling can be swapped in through the environment."""


class ConfigError(ValueError):
    """Setting is present but unusable."""


ENV_LINE_RE = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")


def _parse_value(value: str, where: str) -> str:
    """``"a b" # note`` -> ``a b``; ``plain # note`` -> ``plain``; ``a=b#c`` -> ``a=b#c``."""
    if value[:1] in ('"', "'"):
        quote = value[0]
        end = value.find(quote, 1)
        if end == -1:
            raise ConfigError(f"{where}: unterminated quote in {value!r}")
        rest = value[end + 1 :].strip()
        if rest and not rest.startswith("#"):
            raise ConfigError(f"{where}: unexpected text after the quoted value: {rest!r}")
        return value[1:end]
    if " #" in value or "\t#" in value:
        value = re.split(r"\s#", value, maxsplit=1)[0]
    return value.rstrip()


def load_env_file(path: str | os.PathLike[str] = ".env", override: bool = False) -> dict[str, str]:
    """Load ``KEY=VALUE`` lines from ``.env`` into ``os.environ``. Returns what was applied.

    Handles comments, an optional ``export`` prefix, spaces around ``=``, CRLF endings,
    quoted values, and trailing ``# note``. Shell variables win unless ``override`` is set,
    so a one-off ``CREWOPS_STAGE=demo ...`` beats the file. No file is fine since every
    setting has a default.
    """
    applied: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except FileNotFoundError:
        return applied

    for number, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = ENV_LINE_RE.match(line)
        if not match:
            raise ConfigError(f"{path}:{number}: expected KEY=VALUE, got {line!r}")
        key, rest = match.group(1), match.group(2)
        # "A=   # note" is empty, as in a shell: "#" after a space starts a comment
        value = "" if re.match(r"\s+#", rest) else _parse_value(rest.strip(), f"{path}:{number}")
        if override or key not in os.environ:
            os.environ[key] = value
            applied[key] = value
    return applied


def _get(env: Mapping[str, str], key: str, default: str | None = None) -> str | None:
    value = env.get(key)
    if value is None or not value.strip():
        return default
    return value.strip()


def _int(env: Mapping[str, str], key: str, default: int, minimum: int = 1) -> int:
    raw = _get(env, key)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{key} must be an integer, got {raw!r}") from None
    if value < minimum:
        raise ConfigError(f"{key} must be >= {minimum}, got {value}")
    return value


def _https_url(env: Mapping[str, str], key: str, default: str) -> str:
    url = (_get(env, key, default) or default).rstrip("/")
    if not re.match(r"^https://[a-z0-9.-]+(:\d+)?$", url):
        raise ConfigError(f"{key} must be an https origin such as {default}, got {url!r}")
    return url


@dataclass(frozen=True, slots=True)
class Settings:
    stage: str
    aws_region: str
    concierge_model_id: str
    """The model the traveller's concierge words its answers with."""
    user_pool_id: str | None
    """Cognito pool and app client whose tokens the MCP server accepts. The stack sets
    these on the deployed server, local commands read them from the auth stack."""
    user_pool_client_id: str | None
    qloo_api_url: str = DEFAULT_QLOO_URL
    """Qloo Taste AI API origin. Every call goes from the server, never the browser."""
    qloo_api_key: str | None = None
    """Local runs read the key from ``QLOO_API_KEY``. Deployed services leave this unset and
    read the SecureString at ``qloo_key_parameter`` instead, so the key is in no template,
    environment variable or log."""
    qloo_cache_hours: int = 24
    """How long a Qloo answer is reused. Places and tastes change slowly, the quota doesn't."""

    # -- Derived resource names ---------------------------------------------

    @property
    def prefix(self) -> str:
        return f"groundtime-{self.stage}"

    @property
    def stack_prefix(self) -> str:
        """CloudFormation stacks are ``<stack_prefix>-Data``, ``-Auth`` and ``-Mcp``."""
        return f"Groundtime-{self.stage}"

    @property
    def table_name(self) -> str:
        return f"{self.prefix}-ops"

    @property
    def issuer(self) -> str | None:
        """Expected ``iss`` claim on the pool's tokens."""
        if not self.user_pool_id:
            return None
        return f"https://cognito-idp.{self.aws_region}.amazonaws.com/{self.user_pool_id}"

    @property
    def mcp_runtime_name(self) -> str:
        # AgentCore runtime names don't allow hyphens
        return f"groundtime_{self.stage.replace('-', '_')}_mcp"

    @property
    def mcp_runtime_role(self) -> str:
        return f"{self.prefix}-mcp-runtime"

    @property
    def user_pool_name(self) -> str:
        """Roles are Cognito groups in this pool."""
        return f"{self.prefix}-users"

    @property
    def qloo_key_parameter(self) -> str:
        """SecureString holding the Qloo API key, created by hand with ``aws ssm put-parameter``."""
        return f"/{self.prefix}/qloo/api-key"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env

        stage = _get(env, "CREWOPS_STAGE", "dev")
        if not STAGE_RE.match(stage):
            raise ConfigError(
                f"CREWOPS_STAGE must be 2-20 lowercase letters, digits or hyphens, "
                f"starting with a letter; got {stage!r}"
            )
        return cls(
            stage=stage,
            aws_region=_get(env, "AWS_REGION") or _get(env, "AWS_DEFAULT_REGION", DEFAULT_REGION),
            concierge_model_id=_get(env, "CREWOPS_CONCIERGE_MODEL_ID", DEFAULT_CONCIERGE_MODEL),
            user_pool_id=_get(env, "CREWOPS_USER_POOL_ID"),
            user_pool_client_id=_get(env, "CREWOPS_USER_POOL_CLIENT_ID"),
            qloo_api_url=_https_url(env, "QLOO_API_URL", DEFAULT_QLOO_URL),
            qloo_api_key=_get(env, "QLOO_API_KEY"),
            qloo_cache_hours=_int(env, "CREWOPS_QLOO_CACHE_HOURS", 24),
        )


def shell_exports(path: str | os.PathLike[str] = ".env") -> str:
    """``export`` lines with the ``.env`` values plus resolved region and stage.
    ``scripts/cdk.sh`` evals this so the shell and Python share one ``.env`` parser and
    the same defaults.
    """
    import shlex

    applied = load_env_file(path)
    settings = Settings.from_env()
    values = {**applied, "AWS_REGION": settings.aws_region, "CREWOPS_STAGE": settings.stage}
    return "\n".join(f"export {key}={shlex.quote(value)}" for key, value in values.items())


if __name__ == "__main__":
    print(shell_exports())
