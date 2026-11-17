import { describe, expect, it } from "vitest";

import { initialSearch, searchReducer, type SearchAction, type SearchState } from "./search";

const ev = (name: string, data: Record<string, unknown>): SearchAction => ({ type: "event", name, data });
const card = (id: string) => ({ id, bhk: 2, rent: 30000 }) as never;

describe("searchReducer", () => {
  it("applies a turn's events in order", () => {
    let s: SearchState = searchReducer(initialSearch, { type: "send", text: "2 bhk in hsr" });
    expect(s.busy).toBe(true);
    expect(s.turns.map((t) => t.role)).toEqual(["user", "assistant"]);
    for (const a of [
      ev("filters", { filters: { city: "bangalore" }, chips: [{ field: "bhk", label: "2 BHK" }] }),
      ev("relaxed", { steps: ["raised the budget to ₹44,000"], count: 6 }),
      ev("pins", { pins: [{ id: "a" }, { id: "b" }] }),
      ev("cards", { cards: [card("a"), card("b")] }),
      ev("token", { text: "Found 6." }),
      ev("citations", { claims: [{ text: "x", refs: [] }] }),
      ev("done", { chat_id: "c1" }),
    ]) s = searchReducer(s, a);
    const reply = s.turns[1]!;
    expect(s.chatId).toBe("c1");
    expect(s.busy).toBe(false);
    expect(s.chips).toEqual([{ field: "bhk", label: "2 BHK" }]);
    expect(reply).toMatchObject({ content: "Found 6.", cardIds: ["a", "b"], relaxed: ["raised the budget to ₹44,000"], pending: false });
    expect(Object.keys(s.cards)).toEqual(["a", "b"]);
  });

  it("a chip removal adds only an assistant turn; errors end the turn", () => {
    let s = searchReducer(initialSearch, { type: "send", text: "" });
    expect(s.turns.map((t) => t.role)).toEqual(["assistant"]);
    s = searchReducer(s, ev("error", { code: "model_busy", message: "The AI is busy right now." }));
    expect(s.busy).toBe(false);
    expect(s.turns[0]).toMatchObject({ content: "The AI is busy right now.", error: true, pending: false });
  });
});
