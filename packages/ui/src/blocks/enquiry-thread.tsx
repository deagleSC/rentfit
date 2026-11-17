"use client";

import { Button } from "@rentfit/ui/components/button";
import { Textarea } from "@rentfit/ui/components/textarea";
import { cn } from "@rentfit/ui/lib/utils";
import { ArrowUp } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export interface ThreadMessage {
  id: number;
  mine: boolean;
  body: string;
  created_at: string;
}

export interface ThreadSummary {
  id: string;
  listing_title: string;
  locality: string;
  rent: number;
  other_name: string;
  last_message: string;
  last_message_at: string;
  unread: number;
}

function when(iso: string) {
  return new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
}

/** Enquiry list: one row per conversation, unread count first. */
export function EnquiryList({ items, selected, onSelect }: {
  items: ThreadSummary[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <ul className="divide-y rounded-xl border bg-card" aria-label="Enquiries">
      {items.map((e) => (
        <li key={e.id}>
          <button
            type="button"
            data-testid="enquiry-row"
            onClick={() => onSelect(e.id)}
            className={cn("flex w-full flex-col gap-0.5 px-3 py-2.5 text-left hover:bg-accent", selected === e.id && "bg-accent")}
          >
            <span className="flex items-center justify-between gap-2">
              <span className="truncate font-medium">{e.other_name}</span>
              {e.unread > 0 && (
                <span className="rounded-full bg-primary px-1.5 text-xs text-primary-foreground" aria-label={`${e.unread} unread`}>
                  {e.unread}
                </span>
              )}
            </span>
            <span className="truncate text-xs text-muted-foreground">
              {e.listing_title} · {e.locality}
            </span>
            <span className="truncate text-sm">{e.last_message}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

/** One conversation and a reply box. Contact details are removed by the API. */
export function EnquiryConversation({ title, subtitle, messages, onSend, sending }: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  messages: ThreadMessage[];
  onSend: (body: string) => void;
  sending?: boolean;
}) {
  const [text, setText] = useState("");
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [messages.length]);
  return (
    <div className="flex h-full min-h-[420px] flex-col rounded-xl border bg-card">
      <div className="border-b px-4 py-3">
        <div className="font-medium">{title}</div>
        {subtitle && <div className="text-sm text-muted-foreground">{subtitle}</div>}
      </div>
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-4" aria-live="polite">
        {messages.map((m) => (
          <div key={m.id} data-testid="enquiry-message"
               className={cn("w-fit max-w-[80%] rounded-2xl px-3.5 py-2 text-sm",
                             m.mine ? "ml-auto rounded-br-sm bg-primary text-primary-foreground" : "rounded-bl-sm bg-muted")}>
            <p className="whitespace-pre-line">{m.body}</p>
            <p className={cn("mt-1 text-[11px]", m.mine ? "text-primary-foreground/70" : "text-muted-foreground")}>{when(m.created_at)}</p>
          </div>
        ))}
        <div ref={end} />
      </div>
      <form
        className="flex items-end gap-2 border-t p-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (!text.trim()) return;
          onSend(text.trim());
          setText("");
        }}
      >
        <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} maxLength={2000}
                  aria-label="Reply" placeholder="Write a reply…" className="min-h-11 resize-none" />
        <Button type="submit" size="icon" disabled={!text.trim() || sending} aria-label="Send reply">
          <ArrowUp />
        </Button>
      </form>
      <p className="px-3 pb-2 text-[11px] text-muted-foreground">Phone numbers and emails are removed from messages.</p>
    </div>
  );
}
