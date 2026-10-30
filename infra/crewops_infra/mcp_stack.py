"""The MCP server on AgentCore Runtime.

The runtime runs the code package from ``python -m crewops.mcp.package`` on Python 3.12 and
speaks stateless streamable HTTP. It's a code asset, not a container image, so no Docker.

AgentCore's authorizer only lets in access tokens from the Cognito pool and web client. It
passes the ``Authorization`` header through, and the server checks the token again and acts
as that user.

The execution role gets the table, the concierge's Nova model, the one SSM parameter that
holds the Qloo key, and password resets in the user pool. Nothing else.

Billed per second while a session is active. Idle sessions end after five minutes.
"""

from __future__ import annotations

from pathlib import Path

from aws_cdk import CfnOutput, Duration, Stack
from aws_cdk import aws_bedrockagentcore as agentcore
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from constructs import Construct

from crewops.config import Settings
from crewops_infra.auth_stack import AuthStack

PACKAGE = Path(__file__).resolve().parents[2] / "build" / "mcp_server"
GEO_PREFIXES = ("global.", "apac.", "au.", "us.", "eu.")


def model_arns(model_id: str, region: str, account: str) -> list[str]:
    """What InvokeModel must be allowed on for one model id: the foundation model in this
    region, or, for a cross-region inference profile, the profile and the model wherever
    the profile may route."""
    if model_id.startswith(GEO_PREFIXES):
        base = model_id.split(".", 1)[1]
        return [
            f"arn:aws:bedrock:{region}:{account}:inference-profile/{model_id}",
            f"arn:aws:bedrock:*::foundation-model/{base}",
            f"arn:aws:bedrock:::foundation-model/{base}",
        ]
    return [f"arn:aws:bedrock:{region}::foundation-model/{model_id}"]


class McpStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        settings: Settings,
        table: dynamodb.ITableV2,
        auth: AuthStack,
        package: Path = PACKAGE,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        region, account = self.region, self.account

        # The same trust the construct gives its own role, with a fixed name.
        role = iam.Role(
            self,
            "ExecutionRole",
            role_name=settings.mcp_runtime_role,
            description="Execution role for the Groundtime MCP server",
            assumed_by=iam.ServicePrincipal(
                "bedrock-agentcore.amazonaws.com",
                conditions={
                    "StringEquals": {"aws:SourceAccount": account},
                    "ArnLike": {
                        "aws:SourceArn": f"arn:{self.partition}:bedrock-agentcore:{region}:"
                        f"{account}:runtime/{settings.mcp_runtime_name}*"
                    },
                },
            ),
            max_session_duration=Duration.hours(8),
        )
        self.runtime = agentcore.Runtime(
            self,
            "McpServer",
            runtime_name=settings.mcp_runtime_name,
            description="Groundtime MCP server",
            execution_role=role,
            agent_runtime_artifact=agentcore.AgentRuntimeArtifact.from_code_asset(
                path=str(package),
                runtime=agentcore.AgentCoreRuntime.PYTHON_3_12,
                entrypoint=["main.py"],
            ),
            protocol_configuration=agentcore.ProtocolType.MCP,
            authorizer_configuration=agentcore.RuntimeAuthorizerConfiguration.using_cognito(
                auth.user_pool, [auth.client]
            ),
            request_header_configuration=agentcore.RequestHeaderConfiguration(
                allowlisted_headers=["Authorization"]
            ),
            lifecycle_configuration=agentcore.LifecycleConfiguration(
                idle_runtime_session_timeout=Duration.minutes(5),
                max_lifetime=Duration.hours(2),
            ),
            environment_variables={
                "CREWOPS_STAGE": settings.stage,
                "CREWOPS_REAL_TIME": "1",
                "CREWOPS_USER_POOL_ID": auth.user_pool.user_pool_id,
                "CREWOPS_USER_POOL_CLIENT_ID": auth.client.user_pool_client_id,
                "CREWOPS_CONCIERGE_MODEL_ID": settings.concierge_model_id,
            },
        )

        table.grant_read_write_data(self.runtime)
        self.runtime.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=model_arns(settings.concierge_model_id, region, account),
            )
        )

        # The Qloo API key: a SecureString created by hand, read at run time, so it is in no
        # template, environment variable or log. Only this one parameter.
        self.runtime.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameter"],
                resources=[
                    f"arn:aws:ssm:{region}:{account}:parameter{settings.qloo_key_parameter}"
                ],
            )
        )

        # Admins reset a password from the app (crewops.auth.accounts).
        self.runtime.add_to_role_policy(
            iam.PolicyStatement(
                actions=["cognito-idp:AdminSetUserPassword"],
                resources=[auth.user_pool.user_pool_arn],
            )
        )

        CfnOutput(self, "McpRuntimeArn", value=self.runtime.agent_runtime_arn)
