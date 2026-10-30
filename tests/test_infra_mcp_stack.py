"""Synthesize the MCP stack locally (no AWS access) with a stand-in package."""

import json

import pytest

pytest.importorskip("aws_cdk")

from aws_cdk import App, Environment  # noqa: E402
from aws_cdk.assertions import Template  # noqa: E402
from crewops_infra.auth_stack import AuthStack  # noqa: E402
from crewops_infra.data_stack import DataStack  # noqa: E402
from crewops_infra.mcp_stack import McpStack, model_arns  # noqa: E402

from crewops.config import Settings  # noqa: E402

ENV = Environment(account="111111111111", region="us-east-1")


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    package = tmp_path_factory.mktemp("mcp_server")
    (package / "main.py").write_text("print('stand-in')\n")
    settings = Settings.from_env({"CREWOPS_STAGE": "dev"})
    app = App()
    data = DataStack(app, "Data", settings=settings, env=ENV)
    auth = AuthStack(app, "Auth", settings=settings, env=ENV)
    stack = McpStack(
        app, "Mcp", settings=settings, table=data.table, auth=auth, package=package, env=ENV
    )
    return Template.from_stack(stack)


def test_runtime_speaks_mcp_behind_the_cognito_authorizer(template):
    (runtime,) = template.find_resources("AWS::BedrockAgentCore::Runtime").values()
    p = runtime["Properties"]
    assert p["AgentRuntimeName"] == "groundtime_dev_mcp"
    assert p["ProtocolConfiguration"] == "MCP"
    jwt = p["AuthorizerConfiguration"]["CustomJWTAuthorizer"]
    assert "AllowedClients" in jwt and "openid-configuration" in json.dumps(jwt["DiscoveryUrl"])
    assert p["RequestHeaderConfiguration"]["RequestHeaderAllowlist"] == ["Authorization"]
    code = p["AgentRuntimeArtifact"]["CodeConfiguration"]
    assert code["Runtime"] == "PYTHON_3_12" and code["EntryPoint"] == ["main.py"]
    env = p["EnvironmentVariables"]
    for key in ("CREWOPS_USER_POOL_ID", "CREWOPS_USER_POOL_CLIENT_ID", "CREWOPS_REAL_TIME"):
        assert key in env, key
    assert env["CREWOPS_CONCIERGE_MODEL_ID"] == "global.amazon.nova-2-lite-v1:0"
    assert p["LifecycleConfiguration"]["IdleRuntimeSessionTimeout"] == 300


def statements(template):
    out = []
    for policy in template.find_resources("AWS::IAM::Policy").values():
        out += policy["Properties"]["PolicyDocument"]["Statement"]
    return out


def test_permissions_are_only_what_the_server_needs(template):
    by_action = {}
    for s in statements(template):
        actions = s["Action"] if isinstance(s["Action"], list) else [s["Action"]]
        for a in actions:
            by_action.setdefault(a, []).append(s["Resource"])
    invoke = json.dumps(by_action["bedrock:InvokeModel"])
    assert "inference-profile/global.amazon.nova-2-lite-v1:0" in invoke
    assert "dynamodb:PutItem" in by_action
    assert "cognito-idp:AdminSetUserPassword" in by_action
    assert {a.split(":")[0] for a in by_action} <= {
        "bedrock", "bedrock-agentcore", "cognito-idp", "dynamodb", "ecr", "logs", "ssm",
        "cloudwatch", "xray", "s3",
    }  # fmt: skip
    # The Qloo key is read from its one parameter at run time, never set in the environment.
    assert json.dumps(by_action["ssm:GetParameter"]).count("parameter/groundtime-dev/") == 1
    assert "parameter/groundtime-dev/qloo/api-key" in json.dumps(by_action["ssm:GetParameter"])
    assert "QLOO_API_KEY" not in json.dumps(template.to_json())
    assert "*" not in json.dumps(by_action["bedrock:InvokeModel"]).replace("bedrock:*::", "")


def test_runtime_runs_as_its_own_named_role(template):
    roles = template.find_resources("AWS::IAM::Role").values()
    (role,) = [r for r in roles if r["Properties"].get("RoleName") == "groundtime-dev-mcp-runtime"]
    (trust,) = role["Properties"]["AssumeRolePolicyDocument"]["Statement"]
    assert trust["Principal"] == {"Service": "bedrock-agentcore.amazonaws.com"}
    assert "runtime/groundtime_dev_mcp*" in json.dumps(trust["Condition"]["ArnLike"])
    (runtime,) = template.find_resources("AWS::BedrockAgentCore::Runtime").values()
    assert "McpServerExecutionRole" not in json.dumps(runtime)
    assert "ExecutionRole" in json.dumps(runtime["Properties"]["RoleArn"])
    # The construct still adds its own needs (logs, workload identity) to the role.
    sids = {s.get("Sid") for s in statements(template)}
    assert {"LogGroupAccess", "GetAgentAccessToken"} <= sids


def test_no_conversation_memory_is_kept(template):
    assert template.find_resources("AWS::BedrockAgentCore::Memory") == {}


def test_model_arns():
    assert model_arns("amazon.nova-micro-v1:0", "us-east-1", "1") == [
        "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-micro-v1:0"
    ]
    arns = model_arns("global.amazon.nova-2-lite-v1:0", "us-east-1", "1")
    assert arns[0] == "arn:aws:bedrock:us-east-1:1:inference-profile/global.amazon.nova-2-lite-v1:0"
    assert "arn:aws:bedrock:*::foundation-model/amazon.nova-2-lite-v1:0" in arns
