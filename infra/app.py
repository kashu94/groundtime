"""CDK entry point. Run it through ``scripts/cdk.sh`` from the repository root.

Settings come from ``.env`` and the environment, exactly as for the application, so the
deployed resource names always match what the code expects. The account comes from the AWS
profile named in ``.env`` (``AWS_PROFILE``); access keys stay in ``~/.aws``, never here.
"""

from __future__ import annotations

import os
import sys

from aws_cdk import App, Environment, Tags
from crewops_infra.auth_stack import AuthStack
from crewops_infra.data_stack import DataStack
from crewops_infra.mcp_stack import PACKAGE, McpStack

from crewops.config import Settings, load_env_file


def main() -> None:
    load_env_file()
    settings = Settings.from_env()
    app = App()
    env = Environment(account=os.environ.get("CDK_DEFAULT_ACCOUNT"), region=settings.aws_region)

    data = DataStack(app, f"{settings.stack_prefix}-Data", settings=settings, env=env)
    auth = AuthStack(app, f"{settings.stack_prefix}-Auth", settings=settings, env=env)
    if (PACKAGE / "main.py").exists():
        McpStack(
            app,
            f"{settings.stack_prefix}-Mcp",
            settings=settings,
            table=data.table,
            auth=auth,
            env=env,
        )
    else:
        print(
            "Note: the MCP stack is left out until its package is built "
            "(uv run python -m crewops.mcp.package).",
            file=sys.stderr,
        )

    Tags.of(app).add("project", "groundtime")
    Tags.of(app).add("stage", settings.stage)
    app.synth()


if __name__ == "__main__":
    main()
