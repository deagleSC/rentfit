"use client";

import { messageFor } from "@rentfit/api-client";
import { Conversation, ConversationContent } from "@rentfit/ui/ai-elements/conversation";
import { Button } from "@rentfit/ui/components/button";
import { Textarea } from "@rentfit/ui/components/textarea";
import { cn } from "@rentfit/ui/lib/utils";
import { SendHorizontal, Loader2 } from "lucide-react";
import { useState, type FormEvent, type KeyboardEvent } from "react";
import { toast } from "sonner";

import { useChat, useSendChat, type Change } from "@/lib/listings";

const EXAMPLE = "2BHK in Koramangala, rent 35k, 2 months deposit, semi furnished, family preferred. Lift and power backup.";

export function ChatPanel({ id, onChanges }: { id: string; onChanges: (c: Change[]) => void }) {
  const chat = useChat(id);
  const send = useSendChat(id);
  const [text, setText] = useState("");
  const [pending, setPending] = useState<string | null>(null);

  function submit(e?: FormEvent) {
    e?.preventDefault();
    const message = text.trim();
    if (!message || send.isPending) return;
    setPending(message);
    setText("");
    send.mutate(message, {
      onSuccess: (r) => onChanges(r.changes),
      onError: (err) => {
        toast.error(messageFor(err));
        setText(message);
      },
      onSettled: () => setPending(null),
    });
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) submit();
  }

  const messages = chat.data?.messages ?? [];
  return (
    <section aria-label="Listing chat" className="flex h-[calc(100vh-11rem)] min-h-[420px] flex-col rounded-xl border bg-card">
      <Conversation className="flex-1">
        <ConversationContent className="space-y-3 p-4">
          {messages.length === 0 && !pending ? (
            <div className="space-y-3 text-sm text-muted-foreground">
              <p>Describe your flat in your own words. English or Hindi-English both work.</p>
              <button
                type="button"
                className="rounded-lg border bg-muted/40 p-3 text-left hover:bg-muted"
                onClick={() => setText(EXAMPLE)}
              >
                {EXAMPLE}
              </button>
            </div>
          ) : null}
          {messages.map((m, i) => (
            <Bubble key={i} role={m.role} text={m.content} />
          ))}
          {pending ? (
            <>
              <Bubble role="user" text={pending} />
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" /> Reading that…
              </div>
            </>
          ) : null}
          {messages.length > 0 && !pending && chat.data?.prompt && messages.at(-1)?.role !== "assistant" ? (
            <Bubble role="assistant" text={chat.data.prompt} />
          ) : null}
        </ConversationContent>
      </Conversation>
      <form onSubmit={submit} className="flex items-end gap-2 border-t p-3">
        <label htmlFor="listing-chat-input" className="sr-only">
          Message
        </label>
        <Textarea
          id="listing-chat-input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKey}
          placeholder={chat.data?.prompt ?? "Describe your flat…"}
          rows={2}
          maxLength={2000}
          className="min-h-0 resize-none"
        />
        <Button type="submit" size="icon" disabled={!text.trim() || send.isPending} aria-label="Send">
          <SendHorizontal />
        </Button>
      </form>
    </section>
  );
}

function Bubble({ role, text }: { role: string; text: string }) {
  return (
    <div className={cn("flex", role === "user" ? "justify-end" : "justify-start")}>
      <p
        className={cn(
          "max-w-[85%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm",
          role === "user" ? "bg-primary text-primary-foreground" : "bg-muted",
        )}
      >
        {text}
      </p>
    </div>
  );
}
