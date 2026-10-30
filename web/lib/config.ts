// Server-side settings, written to .env.local by `python -m crewops.web_env` from the
// deployed stacks' outputs. None of them is a secret, and none reaches the browser.

function required(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`${name} is not set; run \`uv run python -m crewops.web_env\` first`);
  }
  return value;
}

export const settings = {
  region: () => process.env.CREWOPS_REGION ?? process.env.AWS_REGION ?? "ap-southeast-2",
  clientId: () => required("CREWOPS_USER_POOL_CLIENT_ID"),
  runtimeArn: () => required("CREWOPS_MCP_RUNTIME_ARN"),
};

export function invocationUrl(region: string, runtimeArn: string): string {
  return (
    `https://bedrock-agentcore.${region}.amazonaws.com/runtimes/` +
    `${encodeURIComponent(runtimeArn)}/invocations?qualifier=DEFAULT`
  );
}
