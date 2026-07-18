export type GlobePoint = {
  a: string;
  b: string;
  miss_km: number;
  relv_km_s: number;
  tca: string;
  pos: [number, number, number]; // TEME km
};

export type GlobeData = {
  generated_at: string;
  earth_radius_km: number;
  points: GlobePoint[];
};

const GLOBE_URL =
  process.env.NEXT_PUBLIC_GLOBE_URL ??
  "https://cdn.jsdelivr.net/gh/anshuman542018/OrbitSense@data/events/globe.json";

export async function loadGlobe(): Promise<GlobeData> {
  try {
    const res = await fetch(GLOBE_URL, { next: { revalidate: 900 } });
    if (res.ok) {
      const data = (await res.json()) as GlobeData;
      if (data.points?.length) return data;
    }
  } catch {
    // fall through to bundled seed
  }
  try {
    const fs = await import("node:fs/promises");
    const path = await import("node:path");
    const raw = await fs.readFile(
      path.join(process.cwd(), "public", "globe.json"),
      "utf8"
    );
    return JSON.parse(raw) as GlobeData;
  } catch {
    return { generated_at: "", earth_radius_km: 6378.137, points: [] };
  }
}
