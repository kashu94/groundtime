"""The web app's settings file, built from stack outputs."""

from crewops.web_env import lines


def test_settings_come_from_the_stack_outputs():
    out = lines(
        "ap-southeast-2",
        {"UserPoolClientId": "client-1"},
        {"McpRuntimeArn": "arn:aws:bedrock-agentcore:ap-southeast-2:111111111111:runtime/x"},
    )
    assert "CREWOPS_REGION=ap-southeast-2" in out
    assert "CREWOPS_USER_POOL_CLIENT_ID=client-1" in out
    assert any(line.startswith("CREWOPS_MCP_RUNTIME_ARN=arn:") for line in out)
    assert not any("SECRET" in line or "PASSWORD" in line for line in out)
