import os

import pytest

from crewops.config import ConfigError, Settings, load_env_file, shell_exports


def test_defaults_without_environment():
    s = Settings.from_env({})
    assert s.stage == "dev"
    assert s.aws_region == "ap-southeast-2"
    assert s.concierge_model_id == "global.amazon.nova-2-lite-v1:0"
    assert s.qloo_api_url == "https://hackathon.api.qloo.com" and s.qloo_api_key is None


def test_resource_names_derive_from_stage():
    s = Settings.from_env({"CREWOPS_STAGE": "demo"})
    assert s.table_name == "groundtime-demo-ops"
    assert s.user_pool_name == "groundtime-demo-users"
    assert s.mcp_runtime_name == "groundtime_demo_mcp"
    assert s.qloo_key_parameter == "/groundtime-demo/qloo/api-key"
    assert s.stack_prefix == "Groundtime-demo"


def test_overrides_are_applied():
    s = Settings.from_env(
        {
            "AWS_REGION": "ap-south-1",
            "CREWOPS_CONCIERGE_MODEL_ID": "apac.amazon.nova-pro-v1:0",
            "CREWOPS_QLOO_CACHE_HOURS": "6",
        }
    )
    assert s.aws_region == "ap-south-1"
    assert s.concierge_model_id == "apac.amazon.nova-pro-v1:0"
    assert s.qloo_cache_hours == 6


def test_falls_back_to_aws_default_region():
    assert Settings.from_env({"AWS_DEFAULT_REGION": "eu-west-1"}).aws_region == "eu-west-1"


def test_empty_values_count_as_unset():
    s = Settings.from_env({"CREWOPS_STAGE": "", "QLOO_API_KEY": "  "})
    assert s.stage == "dev"
    assert s.qloo_api_key is None


@pytest.mark.parametrize("stage", ["Dev", "1dev", "d", "dev_1", "x" * 21])
def test_rejects_bad_stage(stage):
    with pytest.raises(ConfigError, match="CREWOPS_STAGE"):
        Settings.from_env({"CREWOPS_STAGE": stage})


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("CREWOPS_QLOO_CACHE_HOURS", "0"),
        ("CREWOPS_QLOO_CACHE_HOURS", "a day"),
        ("QLOO_API_URL", "http://hackathon.api.qloo.com"),
    ],
)
def test_rejects_bad_numbers(key, value):
    with pytest.raises(ConfigError, match=key):
        Settings.from_env({key: value})


def test_settings_are_immutable():
    s = Settings.from_env({})
    with pytest.raises(AttributeError):
        s.stage = "prod"


@pytest.fixture
def private_environ(monkeypatch):
    """A throwaway copy of the environment, so .env loading cannot leak into other tests."""
    env = dict(os.environ)
    for key in [k for k in env if k.startswith(("CREWOPS_", "AWS_"))]:
        del env[key]
    monkeypatch.setattr(os, "environ", env)
    return env


def test_load_env_file_applies_values_without_overriding_shell(tmp_path, private_environ):
    env = tmp_path / ".env"
    env.write_text(
        "# comment\n"
        "\n"
        "CREWOPS_STAGE=demo\n"
        "export AWS_REGION='eu-west-1'\n"
        'QLOO_API_URL="https://qloo.example"\n'
        "CREWOPS_QLOO_CACHE_HOURS=5  # inline comment\n"
        "AWS_PROFILE=fromfile\n"
    )
    private_environ["AWS_PROFILE"] = "fromshell"

    applied = load_env_file(env)

    assert private_environ["CREWOPS_STAGE"] == "demo"
    assert private_environ["AWS_REGION"] == "eu-west-1"
    assert private_environ["QLOO_API_URL"] == "https://qloo.example"
    assert private_environ["CREWOPS_QLOO_CACHE_HOURS"] == "5"
    assert private_environ["AWS_PROFILE"] == "fromshell"
    assert "AWS_PROFILE" not in applied
    assert Settings.from_env().stage == "demo"


@pytest.mark.parametrize(
    ("line", "value"),
    [
        ("A=crewops  ", "crewops"),
        ("A=crewops\r", "crewops"),
        ("A = crewops", "crewops"),
        ("export   A=crewops", "crewops"),
        ('A="a b" # note', "a b"),
        ("A='x#y'", "x#y"),
        ("A=a=b#c", "a=b#c"),
        ("A=plain # note", "plain"),
        ("A=", ""),
        ("A= # none yet", ""),
        ("A=\t# none yet", ""),
        ("A=#x", "#x"),
    ],
)
def test_env_value_edge_cases(tmp_path, private_environ, line, value):
    env = tmp_path / ".env"
    env.write_bytes((line + "\n").encode())
    load_env_file(env)
    assert private_environ["A"] == value


@pytest.mark.parametrize("line", ["T", 'A="unterminated', 'A="x" trailing'])
def test_env_rejects_malformed_lines(tmp_path, private_environ, line):
    env = tmp_path / ".env"
    env.write_text(line + "\n")
    with pytest.raises(ConfigError, match=r"\.env:1"):
        load_env_file(env)


def test_shell_exports_resolve_region_and_stage_like_python(tmp_path, private_environ):
    env = tmp_path / ".env"
    env.write_text("AWS_PROFILE=crewops\nX='a b'\n")
    private_environ["AWS_DEFAULT_REGION"] = "eu-west-1"

    lines = shell_exports(env).splitlines()

    assert "export AWS_PROFILE=crewops" in lines
    assert "export AWS_REGION=eu-west-1" in lines  # same fallback the Python code uses
    assert "export CREWOPS_STAGE=dev" in lines
    assert "export X='a b'" in lines  # quoted safely for the shell


def test_load_env_file_missing_is_fine(tmp_path, private_environ):
    assert load_env_file(tmp_path / "nope.env") == {}


def test_load_env_file_rejects_garbage(tmp_path, private_environ):
    bad = tmp_path / ".env"
    bad.write_text("this is not a setting\n")
    with pytest.raises(ConfigError, match=r"\.env:1"):
        load_env_file(bad)


def test_env_example_loads_as_documented(private_environ):
    """Copying .env.example to .env must give working settings, not a config error."""
    from pathlib import Path

    example = Path(__file__).resolve().parents[1] / ".env.example"
    load_env_file(example)
    s = Settings.from_env()
    assert s.stage == "dev" and s.aws_region == "ap-southeast-2"
