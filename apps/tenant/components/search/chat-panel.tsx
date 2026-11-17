"use client";

import { Button } from "@rentfit/ui/components/button";
import { Spinner } from "@rentfit/ui/components/spinner";
import { Textarea } from "@rentfit/ui/components/textarea";
import { cn } from "@rentfit/ui/lib/utils";
import { ArrowUp, Info } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { ListingCard, Ref, SearchState, Turn } from "@/lib/search";

import { CitationChip } from "./citation-chip";
import { ListingCardView } from "./listing-card";

const EXAMPLES = [
  "2 BHK in Indiranagar under 45k, near metro",
  "1 bhk for bachelors within 30 min of Manyata Tech Park",
  "Andheri West mein family ke liye 2 bhk, 70k tak",
  "Semi-furnished flat in Powai with a gym",
];

function Reply({ turn, cards, hovered, onHover }: {
  turn: Turn; cards: Record<string, ListingCard>; hovered: string | null; onHover: (id: string | null) => void;
}) {
  // Number this message's sources once, in order of first use.
  const order: Ref[] = [];
  const num = (r: Ref) => {
    let i = order.findIndex((o) => o.kind === r.kind && o.id === r.id);
    if (i === -1) i = order.push(r) - 1;
    return i + 1;
  };
  const shown = turn.cardIds.map((id) => cards[id]).filter((c): c is ListingCard => !!c);
  return (
    <div className="space-y-3" data-testid="assistant-turn">
      {turn.relaxed.length > 0 && (
        <div data-testid="relaxed-notice" className="flex gap-2 rounded-lg border border-dashed bg-muted/50 p-2.5 text-sm">
          <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
          <span>Too few exact matches, so I {turn.relaxed.join(", then ")}.</span>
        </div>
      )}
      {turn.content && <p className={cn("text-sm leading-relaxed", turn.error && "text-destructive")}>{turn.content}</p>}
      {turn.claims.length > 0 && (
        <ul className="space-y-1.5 text-sm leading-relaxed">
          {turn.claims.map((c, i) => (
            <li key={i} className="flex gap-2">
              <span className="text-muted-foreground">•</span>
              <span>
                {c.text}
                {c.refs.map((r) => (
                  <CitationChip key={`${r.kind}-${r.id}`} r={r} n={num(r)} />
                ))}
              </span>
            </li>
          ))}
        </ul>
      )}
      {shown.length > 0 && (
        <div className="space-y-2">
          {shown.map((c, i) => (
            <ListingCardView key={c.id} card={c} index={shown.length > 1 ? i + 1 : undefined}
                             active={hovered === c.id} onHover={onHover} />
          ))}
        </div>
      )}
      {turn.pending && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Spinner /> Searching…
        </div>
      )}
    </div>
  );
}

export function ChatPanel({ state, onSend, onHover }: {
  state: SearchState;
  onSend: (message: string) => void;
  onHover: (id: string | null) => void;
}) {
  const [text, setText] = useState("");
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [state.turns.length]);
  const submit = () => {
    const t = text.trim();
    if (!t || state.busy) return;
    onSend(t);
    setText("");
  };
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto pr-1" aria-live="polite">
        {state.turns.length === 0 && (
          <div className="space-y-3 pt-4">
            <p className="text-sm text-muted-foreground">
              Describe the home you want, in English or Hinglish. Follow up to refine it.
            </p>
            <div className="flex flex-col gap-2">
              {EXAMPLES.map((e) => (
                <button key={e} type="button" onClick={() => onSend(e)}
                        className="rounded-lg border bg-card px-3 py-2 text-left text-sm hover:bg-accent">
                  {e}
                </button>
              ))}
            </div>
          </div>
        )}
        {state.turns.map((t, i) =>
          t.role === "user" ? (
            <div key={i} className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-3.5 py-2 text-sm text-primary-foreground">
              {t.content}
            </div>
          ) : (
            <Reply key={i} turn={t} cards={state.cards} hovered={state.hovered} onHover={onHover} />
          ),
        )}
        <div ref={end} />
      </div>
      <form
        className="mt-3 flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <Textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder={state.turns.length ? "Refine: cheaper, near metro, the 2nd one's commute?" : "2 BHK in HSR Layout under 40k…"}
          aria-label="Message"
          rows={2}
          maxLength={1000}
          className="min-h-11 resize-none"
        />
        <Button type="submit" size="icon" disabled={!text.trim() || state.busy} aria-label="Send">
          <ArrowUp />
        </Button>
      </form>
    </div>
  );
}
