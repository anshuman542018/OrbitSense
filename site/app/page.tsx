import { EventCardView } from "./components/EventCardView";
import { loadFeed } from "./lib/feed";

export const revalidate = 300;

export default async function Home() {
  const feed = await loadFeed();
  const conjunctions = feed.events.filter(
    (e) => e.type === "conjunction_notice"
  ).length;
  const maneuvers = feed.events.length - conjunctions;
  const updated = feed.generated_at
    ? new Date(feed.generated_at).toISOString().replace("T", " ").slice(0, 16)
    : "—";

  return (
    <main className="wrap">
      <section className="hero">
        <p>
          Every day, OrbitSense pulls the public catalog of tracked space
          objects, propagates their orbits, screens for close approaches, and
          detects maneuvers. An AI analyst then explains each event in plain
          language, with the numbers to back it up.
        </p>
        <div className="stat-row">
          <div className="stat">
            <div className="n">{feed.count}</div>
            <div className="l">events in feed</div>
          </div>
          <div className="stat">
            <div className="n">{conjunctions}</div>
            <div className="l">close approaches</div>
          </div>
          <div className="stat">
            <div className="n">{maneuvers}</div>
            <div className="l">maneuvers</div>
          </div>
          <div className="stat">
            <div className="n" style={{ fontSize: 15, paddingTop: 8 }}>
              {updated} UTC
            </div>
            <div className="l">last updated</div>
          </div>
        </div>
      </section>

      <section className="feed">
        {feed.events.length === 0 ? (
          <div className="empty">
            No events loaded yet. The daily pipeline publishes the live feed to
            the data branch.
          </div>
        ) : (
          feed.events.map((card, i) => <EventCardView key={i} card={card} />)
        )}
      </section>

      <footer className="foot">
        <p>
          Built on public data (CelesTrak, Space-Track).{" "}
          <strong>Not an operational safety service.</strong> Conjunctions are
          screening-level estimates from public elements — no collision
          probabilities are claimed. Maneuvers are described conservatively
          (&ldquo;consistent with&rdquo;, never &ldquo;is&rdquo;) with the
          numbers that triggered them.
        </p>
      </footer>
    </main>
  );
}
