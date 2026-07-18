import { FEED_URL, type EventCard } from "../../lib/feed";

// Chat runs on the default Node.js runtime. It answers ONLY from tool results
// over the event feed — the model never free-associates about orbits. Tools:
//   get_events(filter?)         -> events, optionally filtered by type/object
//   query_object(query)         -> events mentioning a NORAD id or name
// Without GEMINI_API_KEY the route degrades to deterministic keyword search,
// so the page works on a zero-cost deploy with no keys.

export const runtime = "nodejs";

type ChatMessage = { role: "user" | "assistant"; content: string };

async function fetchEvents(): Promise<EventCard[]> {
  try {
    const res = await fetch(FEED_URL, { next: { revalidate: 900 } });
    if (res.ok) {
      const feed = await res.json();
      if (feed.events?.length) return feed.events;
    }
  } catch {
    /* fall through to bundled seed */
  }
  // Bundled seed so the copilot works on a zero-cost deploy before the data
  // branch CDN URL is wired up.
  try {
    const fs = await import("node:fs/promises");
    const path = await import("node:path");
    const raw = await fs.readFile(
      path.join(process.cwd(), "public", "feed.json"),
      "utf8"
    );
    return JSON.parse(raw).events ?? [];
  } catch {
    return [];
  }
}

function getEvents(events: EventCard[], filter?: { type?: string; object?: string }) {
  let out = events;
  if (filter?.type) out = out.filter((e) => e.type === filter.type);
  if (filter?.object) {
    const q = filter.object.toLowerCase();
    out = out.filter(
      (e) =>
        JSON.stringify(e.evidence).toLowerCase().includes(q) ||
        e.headline.toLowerCase().includes(q) ||
        e.object_ids.some((id) => String(id) === q)
    );
  }
  return out.slice(0, 20);
}

function keywordAnswer(question: string, events: EventCard[]): string {
  const q = question.toLowerCase();
  const typeHit = [
    "conjunction",
    "maneuver",
    "reboost",
    "orbit_raise",
    "deorbit",
    "station",
  ].find((t) => q.includes(t));
  let hits = events;
  const words = q.replace(/[^a-z0-9 -]/g, " ").split(/\s+/).filter((w) => w.length > 2);
  const named = events.filter((e) =>
    words.some((w) => e.headline.toLowerCase().includes(w))
  );
  if (named.length) hits = named;
  else if (typeHit?.includes("conjunction"))
    hits = events.filter((e) => e.type === "conjunction_notice");
  else if (typeHit)
    hits = events.filter((e) => e.type !== "conjunction_notice");

  if (hits.length === 0)
    return "I don't see any matching events in today's feed. Try a satellite name (e.g. \"Starlink\", \"ISS\") or a type (\"conjunctions\", \"maneuvers\").";

  const lines = hits
    .slice(0, 5)
    .map((e) => `• ${e.headline} — ${e.explanation}`)
    .join("\n\n");
  return `Here is what the feed shows${
    typeHit ? ` for ${typeHit}s` : ""
  }:\n\n${lines}`;
}

async function geminiAnswer(
  question: string,
  history: ChatMessage[],
  events: EventCard[],
  key: string
): Promise<string> {
  const system = `You are the OrbitSense chat copilot. Answer ONLY from the \
EVENTS provided (today's screened feed). Never invent orbital data. If the \
answer is not in the events, say so and suggest a refinement. Cite the numbers \
from the events. Keep answers to a few sentences.`;

  const context = getEvents(events, {
    object: extractObject(question),
  });
  const contents = [
    ...history.map((m) => ({
      role: m.role === "assistant" ? "model" : "user",
      parts: [{ text: m.content }],
    })),
    {
      role: "user",
      parts: [
        {
          text: `EVENTS (JSON):\n${JSON.stringify(
            (context.length ? context : events).slice(0, 15)
          )}\n\nQUESTION: ${question}`,
        },
      ],
    },
  ];

  const res = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${key}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        system_instruction: { parts: [{ text: system }] },
        contents,
        generationConfig: { temperature: 0.3 },
      }),
    }
  );
  if (!res.ok) throw new Error(`gemini ${res.status}`);
  const data = await res.json();
  return data.candidates?.[0]?.content?.parts?.[0]?.text ?? "(no answer)";
}

function extractObject(q: string): string | undefined {
  const m = q.match(/\b(\d{4,6})\b/);
  if (m) return m[1];
  const known = ["starlink", "iss", "noaa", "flock", "lemur", "oneweb", "css"];
  const w = q.toLowerCase();
  return known.find((k) => w.includes(k));
}

export async function POST(req: Request) {
  const { message, history = [] } = (await req.json()) as {
    message: string;
    history?: ChatMessage[];
  };
  if (!message || typeof message !== "string") {
    return Response.json({ error: "message required" }, { status: 400 });
  }

  const events = await fetchEvents();
  const key = process.env.GEMINI_API_KEY;

  let answer: string;
  if (key) {
    try {
      answer = await geminiAnswer(message, history, events, key);
    } catch {
      answer = keywordAnswer(message, events);
    }
  } else {
    answer = keywordAnswer(message, events);
  }

  return Response.json({ answer, grounded_events: events.length });
}
