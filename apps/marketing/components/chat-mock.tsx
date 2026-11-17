import { Home, Info, TrainFront, X } from "lucide-react";

/** A static picture of one search exchange, matching what the tenant app shows. Sample data. */
export function ChatMock() {
  return (
    <figure className="rounded-2xl border bg-card p-4 shadow-lg" aria-label="Example search conversation">
      <div className="mb-3 flex flex-wrap gap-1.5" aria-hidden>
        {["Koramangala", "2 BHK", "Up to ₹40k", "Metro ≤ 1 km"].map((c) => (
          <span key={c} className="inline-flex items-center gap-1 rounded-md bg-secondary px-2 py-0.5 text-xs font-medium text-secondary-foreground">
            {c} <X className="size-3" />
          </span>
        ))}
      </div>
      <div className="space-y-3 text-sm">
        <p className="ml-auto w-fit rounded-2xl rounded-br-sm bg-primary px-3.5 py-2 text-primary-foreground">
          2 bhk in Koramangala under 40k, metro ke paas
        </p>
        <div className="flex gap-2 rounded-lg border border-dashed bg-muted/50 p-2.5 text-xs">
          <Info className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
          Too few exact matches, so I added nearby areas (Ejipura, BTM Layout).
        </div>
        <p>I found 6 homes that match.</p>
        <ul className="space-y-1">
          <li>• A semi-furnished 2 BHK in Ejipura for ₹30,000, 600 m from the metro. <Cite n={1} /></li>
          <li>• Ejipura has 12 schools and 3 parks within the area. <Cite n={2} /></li>
        </ul>
        {[
          { rent: "₹30k", where: "2 BHK · Ejipura", tag: "Semi-furnished", metro: "600 m" },
          { rent: "₹28k", where: "2 BHK · BTM Layout", tag: "Furnished", metro: "850 m" },
        ].map((c, i) => (
          <div key={c.where} className="flex gap-3 rounded-xl border bg-background p-2">
            <div className="relative flex size-14 shrink-0 items-center justify-center rounded-lg bg-muted">
              <Home className="size-6 text-muted-foreground" />
              <span className="absolute left-1 top-1 rounded bg-background px-1 text-[10px] font-medium">{i + 1}</span>
            </div>
            <div className="space-y-1">
              <div><span className="font-semibold">{c.rent}</span> <span className="text-muted-foreground">{c.where}</span></div>
              <div className="flex gap-1 text-[11px]">
                <span className="rounded-md bg-secondary px-1.5 py-0.5 text-secondary-foreground">{c.tag}</span>
                <span className="inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5"><TrainFront className="size-3" />{c.metro}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
      <figcaption className="mt-3 text-xs text-muted-foreground">Illustration with sample data.</figcaption>
    </figure>
  );
}

function Cite({ n }: { n: number }) {
  return (
    <span className="ml-0.5 inline-flex size-4 items-center justify-center rounded-full bg-primary/10 align-middle text-[10px] font-medium text-primary">
      {n}
    </span>
  );
}
