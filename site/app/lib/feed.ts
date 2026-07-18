export type EventCard = {
  type: string;
  headline: string;
  explanation: string;
  confidence: "high" | "low";
  evidence: Record<string, unknown>;
  object_ids: number[];
  tca_or_epoch: string;
  generated_at: string;
  narrator: string;
};

export type Feed = {
  generated_at: string;
  count: number;
  events: EventCard[];
};

// The daily pipeline commits feed.json to the repo's `data` branch; jsDelivr
// serves it from the CDN with no server on our side. A bundled seed in
// /public/feed.json keeps the page working locally and on first deploy.
export const FEED_URL =
  process.env.NEXT_PUBLIC_FEED_URL ??
  "https://cdn.jsdelivr.net/gh/anshuman542018/OrbitSense@data/events/feed.json";

export async function loadFeed(): Promise<Feed> {
  // Live feed from the data branch CDN.
  try {
    const res = await fetch(FEED_URL, { next: { revalidate: 900 } });
    if (res.ok) {
      const feed = (await res.json()) as Feed;
      if (feed.events?.length) return feed;
    }
  } catch {
    // fall through to bundled seed
  }
  // Bundled seed (public/feed.json) read from the filesystem — works during
  // server render where a relative fetch has no origin, and before the CDN
  // URL is wired up.
  try {
    const fs = await import("node:fs/promises");
    const path = await import("node:path");
    const raw = await fs.readFile(
      path.join(process.cwd(), "public", "feed.json"),
      "utf8"
    );
    return JSON.parse(raw) as Feed;
  } catch {
    return { generated_at: new Date().toISOString(), count: 0, events: [] };
  }
}
