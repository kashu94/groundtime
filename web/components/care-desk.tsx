import { Headset, Phone } from "lucide-react";

import type { CareDesk as Desk } from "@/lib/groundtime";

/** The customer care line, for a traveller who would rather talk to someone. */
export function CareDesk({ desk }: { desk: Desk }) {
  return (
    <section className="rounded-lg border border-line bg-surface p-4">
      <p className="flex items-center gap-2 text-sm font-semibold">
        <Headset size={15} className="text-accent" /> {desk.name}
      </p>
      <a
        href={`tel:${desk.phone.replace(/\s+/g, "")}`}
        className="mt-2 inline-flex items-center gap-2 font-mono text-lg font-semibold tracking-tight text-foreground hover:text-accent"
      >
        <Phone size={15} /> {desk.phone}
      </a>
      <p className="mt-1 text-xs text-muted">
        {desk.hours}. Call about your trip, a delay, or anything your plan doesn&apos;t answer.
      </p>
    </section>
  );
}
