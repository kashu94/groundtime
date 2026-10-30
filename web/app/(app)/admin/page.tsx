"use client";

import { Copy, KeyRound, Users } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { useMe } from "@/components/me";
import { Button, Empty, Mono, Notice, Panel, Spinner } from "@/components/ui";
import { tool } from "@/lib/client";
import type { Account } from "@/lib/groundtime";

const ROLE: Record<string, string> = {
  traveller: "Traveller",
  crew: "Crew",
  customer_care: "Customer care",
  admin: "Admin",
};

type Reset = { username: string; password: string; note: string };

export default function Admin() {
  const me = useMe();
  const isAdmin = me.roles.includes("admin");
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [reset, setReset] = useState<Reset | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(() => {
    tool<Account[]>("team_accounts").then(setAccounts, (err: Error) => setError(err.message));
  }, []);
  useEffect(() => {
    if (isAdmin) load();
  }, [isAdmin, load]);

  if (!isAdmin) return <Notice>Only an admin manages accounts.</Notice>;

  async function resetPassword(username: string) {
    if (!window.confirm(`Give ${username} a new password? Their old one stops working at once.`)) return;
    setBusy(username);
    setError(null);
    setReset(null);
    setCopied(false);
    try {
      setReset(await tool<Reset>("reset_password", { username }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reset the password.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-xl font-semibold tracking-tight">Admin</h1>
        <p className="mt-1 text-sm text-muted">
          Every sign-in and its roles. A new password is shown once, here; pass it on in person.
        </p>
      </header>

      {error && <Notice tone="error">{error}</Notice>}
      {reset && (
        <div className="flex flex-wrap items-center gap-3 rounded-md border border-[#b7e9c8] bg-ok-soft px-3 py-2 text-sm text-[#04250e]">
          <span>
            New password for <b>{reset.username}</b>: <Mono className="font-semibold">{reset.password}</Mono>
          </span>
          <Button
            tone="ghost"
            onClick={() =>
              navigator.clipboard.writeText(reset.password).then(
                () => setCopied(true),
                () => undefined,
              )
            }
          >
            <Copy size={13} /> {copied ? "Copied" : "Copy"}
          </Button>
          <span className="text-xs">{reset.note}</span>
        </div>
      )}

      <Panel title="Accounts" icon={<Users size={14} className="text-accent" />}>
        {!accounts ? (
          error ? null : (
            <Spinner className="text-muted" />
          )
        ) : accounts.length === 0 ? (
          <Empty icon={<Users size={22} />}>No accounts yet.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-muted">
                <tr className="border-b border-rule">
                  <th className="py-2 pr-3 font-medium">Username</th>
                  <th className="py-2 pr-3 font-medium">Name</th>
                  <th className="py-2 pr-3 font-medium">Roles</th>
                  <th className="py-2 pr-3 font-medium">Record</th>
                  <th className="py-2 font-medium" />
                </tr>
              </thead>
              <tbody>
                {accounts.map((a) => (
                  <tr key={a.username} className="border-b border-rule last:border-0">
                    <td className="py-2 pr-3">
                      <Mono>{a.username}</Mono>
                    </td>
                    <td className="py-2 pr-3">{a.name ?? "—"}</td>
                    <td className="py-2 pr-3 text-xs">{a.roles.map((r) => ROLE[r] ?? r).join(", ")}</td>
                    <td className="py-2 pr-3">
                      <Mono className="text-xs text-muted">{a.crew_id ?? a.traveller_id ?? "—"}</Mono>
                    </td>
                    <td className="py-2 text-right">
                      {a.may_reset && (
                        <Button tone="ghost" disabled={busy !== null} onClick={() => resetPassword(a.username)}>
                          {busy === a.username ? <Spinner /> : <KeyRound size={13} />} Reset password
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
