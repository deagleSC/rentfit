"use client";

import { messageFor, readSSEEvents, type components } from "@rentfit/api-client";
import { useCallback, useReducer, useRef } from "react";

import { env } from "./env";
import { supabase } from "./supabase";

export type ListingCard = components["schemas"]["ListingCard"];
export type Pin = components["schemas"]["Pin"];
export type SearchFilters = components["schemas"]["SearchFilters"];
export type Chip = { field: string; label: string };
export type Ref = { kind: "listing" | "note"; id: string; label: string; text?: string };
export type Claim = { text: string; refs: Ref[] };
export type Bbox = [number, number, number, number];

export interface Turn {
  role: "user" | "assistant";
  content: string;
  claims: Claim[];
  cardIds: string[];
  relaxed: string[];
  question?: boolean;
  error?: boolean;
  pending?: boolean;
}

export interface SearchState {
  chatId: string | null;
  turns: Turn[];
  cards: Record<string, ListingCard>;
  pins: Pin[];
  chips: Chip[];
  filters: SearchFilters | null;
  busy: boolean;
  hovered: string | null;
}

export type SearchAction =
  | { type: "load"; chatId: string; turns: Turn[]; cards: ListingCard[]; pins: Pin[]; chips: Chip[]; filters: SearchFilters }
  | { type: "send"; text: string }
  | { type: "event"; name: string; data: Record<string, unknown> }
  | { type: "fail"; message: string }
  | { type: "hover"; id: string | null };

export const initialSearch: SearchState = {
  chatId: null, turns: [], cards: {}, pins: [], chips: [], filters: null, busy: false, hovered: null,
};

function patchLast(turns: Turn[], patch: (t: Turn) => Turn): Turn[] {
  const last = turns[turns.length - 1];
  return last?.role === "assistant" ? [...turns.slice(0, -1), patch(last)] : turns;
}

/** Pure reducer: the SSE events of a turn, applied in order (frontend plan §8.1). */
export function searchReducer(s: SearchState, a: SearchAction): SearchState {
  switch (a.type) {
    case "load":
      return {
        ...s, chatId: a.chatId, turns: a.turns, pins: a.pins, chips: a.chips, filters: a.filters,
        cards: Object.fromEntries(a.cards.map((c) => [c.id, c])),
      };
    case "send": {
      const user: Turn = { role: "user", content: a.text, claims: [], cardIds: [], relaxed: [] };
      const reply: Turn = { role: "assistant", content: "", claims: [], cardIds: [], relaxed: [], pending: true };
      return { ...s, busy: true, turns: [...s.turns, ...(a.text ? [user] : []), reply] };
    }
    case "hover":
      return { ...s, hovered: a.id };
    case "fail":
      return {
        ...s, busy: false,
        turns: patchLast(s.turns, (t) => ({ ...t, content: a.message, error: true, pending: false })),
      };
    case "event": {
      const d = a.data;
      switch (a.name) {
        case "filters":
          return { ...s, filters: d.filters as SearchFilters, chips: d.chips as Chip[] };
        case "question":
          return { ...s, turns: patchLast(s.turns, (t) => ({ ...t, content: d.text as string, question: true })) };
        case "relaxed":
          return { ...s, turns: patchLast(s.turns, (t) => ({ ...t, relaxed: d.steps as string[] })) };
        case "pins":
          return { ...s, pins: d.pins as Pin[] };
        case "cards": {
          const cards = d.cards as ListingCard[];
          return {
            ...s,
            cards: { ...s.cards, ...Object.fromEntries(cards.map((c) => [c.id, c])) },
            turns: patchLast(s.turns, (t) => ({ ...t, cardIds: cards.map((c) => c.id) })),
          };
        }
        case "token":
          return { ...s, turns: patchLast(s.turns, (t) => ({ ...t, content: t.content + (d.text as string) })) };
        case "citations":
          return { ...s, turns: patchLast(s.turns, (t) => ({ ...t, claims: d.claims as Claim[] })) };
        case "done":
          return { ...s, busy: false, chatId: d.chat_id as string, turns: patchLast(s.turns, (t) => ({ ...t, pending: false })) };
        case "error":
          return searchReducer(s, { type: "fail", message: d.message as string });
        default:
          return s;
      }
    }
  }
}

export interface SendOptions {
  message?: string;
  bbox?: Bbox;
  remove_filters?: string[];
  filters?: SearchFilters;
}

/** The search conversation: state plus `send`, which streams one turn. */
export function useSearch(onChat?: (chatId: string) => void) {
  const [state, dispatch] = useReducer(searchReducer, initialSearch);
  const chatRef = useRef<string | null>(null);
  chatRef.current = state.chatId;

  const send = useCallback(
    async (opts: SendOptions) => {
      dispatch({ type: "send", text: opts.message ?? "" });
      try {
        const token = (await supabase().auth.getSession()).data.session?.access_token;
        const res = await fetch(`${env.apiUrl}/v1/tenant/search/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
          body: JSON.stringify({ chat_id: chatRef.current, ...opts, message: opts.message ?? "" }),
        });
        let created: string | null = null;
        await readSSEEvents(res, (name, data) => {
          if (name === "done") created = (data as { chat_id: string }).chat_id;
          dispatch({ type: "event", name, data: data as Record<string, unknown> });
        });
        if (created && created !== chatRef.current) onChat?.(created);
      } catch (e) {
        dispatch({ type: "fail", message: messageFor(e) });
      }
    },
    [onChat],
  );
  return { state, dispatch, send };
}
