import { Globe } from "../components/Globe";
import { loadGlobe } from "../lib/globe";

export const revalidate = 900;

export default async function GlobePage() {
  const data = await loadGlobe();
  return (
    <main className="wrap">
      <section className="hero" style={{ paddingBottom: 12 }}>
        <p>
          Every close approach OrbitSense screened this window, plotted at its
          point of closest approach in Earth-centered inertial coordinates.
          Color runs from slow co-orbital drift (blue) to fast plane crossings
          (amber). Screening-level positions from public elements.
        </p>
      </section>
      {data.points.length === 0 ? (
        <div className="empty">No conjunction points loaded yet.</div>
      ) : (
        <Globe points={data.points} />
      )}
      <p style={{ color: "var(--muted)", fontSize: 13, paddingBottom: 40 }}>
        {data.points.length} conjunction points shown.
      </p>
    </main>
  );
}
