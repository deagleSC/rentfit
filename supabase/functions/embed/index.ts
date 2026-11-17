// Embeddings for search (backend plan §9): gte-small via Supabase's built-in inference (free, no
// external provider). 384 dimensions, mean-pooled and normalised, so cosine = dot product.
//
// POST { "inputs": ["text", ...] }  →  { "embeddings": [[...384 floats], ...] }
// Called only by the API and jobs, with the shared secret in `x-embed-key` (EMBED_FUNCTION_KEY).
// Deployed with --no-verify-jwt because callers are servers, not signed-in users.

const session = new Supabase.ai.Session("gte-small");
const MAX_INPUTS = 64;
const MAX_CHARS = 2000;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function sameSecret(a: string, b: string): boolean {
  if (!a || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return json({ error: "method_not_allowed" }, 405);
  const secret = Deno.env.get("EMBED_FUNCTION_KEY") ?? "";
  if (!sameSecret(req.headers.get("x-embed-key") ?? "", secret)) return json({ error: "unauthorized" }, 401);

  let inputs: unknown;
  try {
    inputs = (await req.json()).inputs;
  } catch {
    return json({ error: "invalid_json" }, 400);
  }
  if (!Array.isArray(inputs) || inputs.length === 0 || inputs.length > MAX_INPUTS ||
      !inputs.every((t) => typeof t === "string" && t.trim().length > 0)) {
    return json({ error: "inputs must be 1-64 non-empty strings" }, 422);
  }

  const embeddings: number[][] = [];
  for (const text of inputs as string[]) {
    const out = await session.run(text.slice(0, MAX_CHARS), { mean_pool: true, normalize: true });
    embeddings.push(Array.from(out as number[]));
  }
  return json({ embeddings });
});
