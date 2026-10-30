import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

type Tone = "primary" | "secondary" | "danger" | "ghost" | "accent";

export function Button({
  tone = "primary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { tone?: Tone }) {
  const tones: Record<Tone, string> = {
    primary: "bg-brand text-brand-ink hover:bg-[#2a2c2f]",
    accent: "bg-accent text-white hover:bg-[#184d7d]",
    secondary: "bg-surface text-foreground border border-control hover:bg-sunken",
    danger: "bg-critical text-white hover:bg-[#a51e23]",
    ghost: "text-muted hover:text-foreground hover:bg-sunken",
  };
  return (
    <button
      className={cx(
        "inline-flex min-h-8 items-center justify-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium",
        "transition-colors disabled:cursor-not-allowed disabled:opacity-60",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
        tones[tone],
        className,
      )}
      {...props}
    />
  );
}

export function Panel({
  title,
  icon,
  action,
  children,
  className,
  bodyClassName,
}: {
  title?: ReactNode;
  icon?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cx("flex min-h-0 flex-col rounded-lg border border-line bg-surface", className)}>
      {title && (
        <header className="flex min-h-12 items-center justify-between gap-3 border-b border-rule px-5 py-2.5">
          <h2 className="flex items-center gap-2 text-[15px] font-semibold text-foreground [&_svg]:text-muted">
            {icon}
            {title}
          </h2>
          {action}
        </header>
      )}
      <div className={cx("min-h-0 flex-1 p-5", bodyClassName)}>{children}</div>
    </section>
  );
}

export function Field({
  label,
  hint,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="font-medium text-foreground">{label}</span>
      <input
        className="h-10 rounded-md border border-control bg-surface px-3 outline-none transition-colors focus:border-accent focus:ring-2 focus:ring-accent/20"
        {...props}
      />
      {hint && <span className="text-xs text-muted">{hint}</span>}
    </label>
  );
}

/** Flight numbers, times and ids in monospace, so KS434 and 18:40 read at a glance. */
export function Mono({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cx("font-mono text-[0.92em] tracking-tight", className)}>{children}</span>;
}

export function Notice({ tone = "info", children }: { tone?: "info" | "error" | "ok"; children: ReactNode }) {
  const tones = {
    info: "border-[#cfe0ef] bg-accent-soft text-[#173f63]",
    error: "border-[#f5c2bd] bg-critical-soft text-[#831c1e]",
    ok: "border-[#b7e9c8] bg-ok-soft text-[#04250e]",
  };
  return <p className={cx("rounded-md border px-3 py-2 text-sm", tones[tone])}>{children}</p>;
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      aria-label="Loading"
      className={cx(
        "inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent",
        className,
      )}
    />
  );
}

export function Empty({ icon, children }: { icon?: ReactNode; children: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10 text-center text-sm text-muted">
      {icon}
      {children}
    </div>
  );
}

export function day(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso);
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "UTC" });
}
