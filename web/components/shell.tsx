"use client";

import { HeartHandshake, LogOut, Luggage, Menu, Plane, Settings, UserRound, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { signOut } from "@/lib/client";
import { homeFor, viewsFor } from "@/lib/roles";

import { useMe } from "./me";
import { cx } from "./ui";

export function Shell({ children }: { children: ReactNode }) {
  const [menu, setMenu] = useState(false);
  // The frame: sidebar and top bar share one tint with no rule between them; the work sits
  // on a white sheet inset 8px from the window's right and bottom edges.
  return (
    <div className="flex min-h-screen overflow-x-clip bg-background">
      <aside className="sticky top-0 hidden h-screen w-[228px] shrink-0 flex-col px-3 pb-3 lg:flex">
        <Brand />
        <Nav />
        <Account />
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar onMenu={() => setMenu(true)} />
        <main className="mb-0 flex-1 border-line bg-surface px-4 py-6 sm:px-6 lg:mb-2 lg:mr-2 lg:rounded-2xl lg:border lg:px-8">
          {children}
        </main>
      </div>
      {menu && <MenuSheet onClose={() => setMenu(false)} />}
    </div>
  );
}

const ICONS: Record<string, typeof Plane> = {
  "/trip": Luggage,
  "/crew": UserRound,
  "/care": HeartHandshake,
  "/admin": Settings,
};

function Brand() {
  const me = useMe();
  return (
    <Link href={homeFor(me.roles)} className="flex h-12 items-center gap-2.5 px-2">
      <span className="grid h-7 w-7 place-items-center rounded-md bg-accent text-white">
        <Plane size={15} strokeWidth={2} />
      </span>
      <span className="text-[15px] font-semibold tracking-tight">Groundtime</span>
      <span className="text-xs text-muted">with Qloo</span>
    </Link>
  );
}

function Nav() {
  const me = useMe();
  const path = usePathname();
  const views = viewsFor(me.roles);
  return (
    <nav aria-label="Views" className="mt-3 flex flex-col gap-0.5">
      {views.map((v) => {
        const Icon = ICONS[v.href] ?? Plane;
        const active = path.startsWith(v.href);
        return (
          <Link
            key={v.href}
            href={v.href}
            aria-current={active ? "page" : undefined}
            title={v.hint}
            className={cx(
              "flex h-8 items-center gap-2.5 rounded-md px-2.5 text-sm transition-colors",
              active ? "bg-active font-medium text-foreground" : "text-[#4b4d50] hover:bg-active/60",
            )}
          >
            <Icon size={16} strokeWidth={1.6} className={active ? "text-foreground" : "text-muted"} />
            {v.label}
          </Link>
        );
      })}
    </nav>
  );
}

function Account() {
  const me = useMe();
  const router = useRouter();
  return (
    <div className="mt-auto flex items-center gap-2 rounded-md px-2 py-2">
      <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-active text-xs font-semibold uppercase text-foreground">
        {me.user_id.slice(0, 1)}
      </span>
      <span className="min-w-0 flex-1 leading-tight">
        <span className="block truncate text-sm font-medium">{me.user_id}</span>
        <span className="block truncate text-xs text-muted">
          {me.roles.join(", ").replace(/_/g, " ")}
          {me.crew_id && <> · {me.crew_id}</>}
          {me.traveller_id && <> · {me.traveller_id}</>}
        </span>
      </span>
      <button
        className="rounded-md p-1.5 text-muted transition-colors hover:bg-active hover:text-foreground"
        title="Sign out"
        aria-label="Sign out"
        onClick={async () => {
          await signOut().catch(() => undefined);
          router.replace("/login");
        }}
      >
        <LogOut size={16} />
      </button>
    </div>
  );
}

function TopBar({ onMenu }: { onMenu: () => void }) {
  const me = useMe();
  const path = usePathname();
  const views = viewsFor(me.roles);
  const current = views.find((v) => path.startsWith(v.href)) ?? views[0];

  return (
    <header className="sticky top-0 z-30 flex h-12 shrink-0 items-center gap-3 bg-background px-4 lg:static lg:pl-1 lg:pr-3">
      <button
        className="-ml-1 rounded-md p-1.5 text-muted hover:bg-active hover:text-foreground lg:hidden"
        onClick={onMenu}
        aria-label="Open the menu"
      >
        <Menu size={18} />
      </button>
      <span className="lg:hidden">
        <Brand />
      </span>
      {current && (
        <p className="hidden min-w-0 truncate text-sm text-muted lg:block">
          {current.label} <span className="text-[#9a9c9f]">·</span> {current.hint}
        </p>
      )}
    </header>
  );
}

/** The phone's navigation: the sidebar's content in a sheet over the screen. */
function MenuSheet({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const escape = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
      <button className="absolute inset-0 bg-black/30" aria-label="Close the menu" onClick={onClose} />
      <div className="absolute inset-y-0 left-0 flex w-[280px] flex-col bg-background px-3 pb-3 shadow-xl">
        <div className="flex items-center justify-between">
          <Brand />
          <button className="rounded-md p-1.5 text-muted hover:bg-active" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>
        {/* choosing a view closes the sheet */}
        <div onClick={onClose}>
          <Nav />
        </div>
        <Account />
      </div>
    </div>
  );
}
