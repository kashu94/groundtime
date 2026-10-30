"""Write the web app's settings from the deployed stacks' outputs.

    uv run python -m crewops.web_env             # writes web/.env.local

The web app needs the region, the Cognito app client and the MCP runtime. They are read from
the ``Groundtime-<stage>-Auth`` and ``-Mcp`` stack outputs, so nothing is copied by hand.
The file holds no secret (the app client has none) and is ignored by git. For the hosted
app, the same values go into Amplify's environment variables.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parents[2] / "web"


def lines(region: str, auth: dict, mcp: dict) -> list[str]:
    return [
        "# Written by `python -m crewops.web_env` from the stack outputs. Not committed.",
        f"CREWOPS_REGION={region}",
        f"CREWOPS_USER_POOL_CLIENT_ID={auth['UserPoolClientId']}",
        f"CREWOPS_MCP_RUNTIME_ARN={mcp['McpRuntimeArn']}",
    ]


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=WEB_DIR / ".env.local")
    args = parser.parse_args(argv)

    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    from crewops.config import Settings, load_env_file
    from crewops.mcp.client import outputs

    load_env_file()
    profile = os.environ.get("AWS_PROFILE")
    if not profile or profile == "default":
        print("Set AWS_PROFILE (for example in .env) to a named profile.", file=sys.stderr)
        return 1
    settings = Settings.from_env()
    try:
        cloudformation = boto3.Session(region_name=settings.aws_region).client("cloudformation")
        auth = outputs(cloudformation, f"{settings.stack_prefix}-Auth")
        mcp = outputs(cloudformation, f"{settings.stack_prefix}-Mcp")
        body = lines(settings.aws_region, auth, mcp)
    except (ClientError, BotoCoreError) as exc:
        print(f"AWS error: {exc}", file=sys.stderr)
        return 1
    except KeyError as exc:
        print(f"A stack output is missing: {exc}. Deploy the stacks first.", file=sys.stderr)
        return 1
    args.out.write_text("\n".join(body) + "\n")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
