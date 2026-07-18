"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import type { GlobePoint } from "../lib/globe";

// Self-contained 3D Earth: a wireframe globe with a fresnel glow and the
// week's conjunction points plotted at their TEME positions. No external
// textures (CSP-safe, zero-cost), procedural everything.

const EARTH_KM = 6378.137;
const SCALE = 1 / EARTH_KM; // Earth radius = 1 scene unit

export function Globe({ points }: { points: GlobePoint[] }) {
  const mountRef = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState<GlobePoint | null>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const width = mount.clientWidth;
    const height = mount.clientHeight;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.01, 100);
    camera.position.set(0, 0.35, 3.0);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    mount.appendChild(renderer.domElement);

    // Earth: solid dark sphere + glowing wireframe overlay.
    const earthGroup = new THREE.Group();
    scene.add(earthGroup);

    const solid = new THREE.Mesh(
      new THREE.SphereGeometry(1, 48, 48),
      new THREE.MeshBasicMaterial({ color: 0x0a1a33 })
    );
    earthGroup.add(solid);

    const wire = new THREE.Mesh(
      new THREE.SphereGeometry(1.001, 32, 24),
      new THREE.MeshBasicMaterial({
        color: 0x2a6df0,
        wireframe: true,
        transparent: true,
        opacity: 0.25,
      })
    );
    earthGroup.add(wire);

    // Atmospheric glow (back-side fresnel).
    const glow = new THREE.Mesh(
      new THREE.SphereGeometry(1.15, 48, 48),
      new THREE.ShaderMaterial({
        transparent: true,
        side: THREE.BackSide,
        uniforms: {},
        vertexShader: `
          varying float intensity;
          void main() {
            vec3 n = normalize(normalMatrix * normal);
            vec3 v = normalize((modelViewMatrix * vec4(position,1.0)).xyz);
            intensity = pow(1.0 - abs(dot(n, v)), 2.0);
            gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0);
          }`,
        fragmentShader: `
          varying float intensity;
          void main() {
            gl_FragColor = vec4(0.35, 0.6, 1.0, 1.0) * intensity;
          }`,
      })
    );
    scene.add(glow);

    // Conjunction points.
    const geom = new THREE.BufferGeometry();
    const positions = new Float32Array(points.length * 3);
    const colors = new Float32Array(points.length * 3);
    points.forEach((p, i) => {
      positions[i * 3] = p.pos[0] * SCALE;
      positions[i * 3 + 1] = p.pos[2] * SCALE; // TEME z -> scene up
      positions[i * 3 + 2] = -p.pos[1] * SCALE;
      // Color by closing speed: slow (blue) -> fast (amber/red).
      const t = Math.min(p.relv_km_s / 14, 1);
      colors[i * 3] = 0.3 + 0.7 * t;
      colors[i * 3 + 1] = 0.6 - 0.3 * t;
      colors[i * 3 + 2] = 1.0 - 0.8 * t;
    });
    geom.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geom.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    const cloud = new THREE.Points(
      geom,
      new THREE.PointsMaterial({
        size: 0.03,
        vertexColors: true,
        transparent: true,
        opacity: 0.95,
      })
    );
    scene.add(cloud);

    // Starfield backdrop.
    const starGeom = new THREE.BufferGeometry();
    const starPos = new Float32Array(1500 * 3);
    for (let i = 0; i < starPos.length; i++)
      starPos[i] = (Math.random() - 0.5) * 60;
    starGeom.setAttribute("position", new THREE.BufferAttribute(starPos, 3));
    scene.add(
      new THREE.Points(
        starGeom,
        new THREE.PointsMaterial({ color: 0x8899bb, size: 0.05 })
      )
    );

    // Drag to rotate, wheel to zoom.
    let dragging = false;
    let px = 0;
    let py = 0;
    const rot = { x: 0.3, y: 0 };
    const onDown = (e: PointerEvent) => {
      dragging = true;
      px = e.clientX;
      py = e.clientY;
    };
    const onUp = () => (dragging = false);
    const onMove = (e: PointerEvent) => {
      if (!dragging) return;
      rot.y += (e.clientX - px) * 0.005;
      rot.x += (e.clientY - py) * 0.005;
      rot.x = Math.max(-1.4, Math.min(1.4, rot.x));
      px = e.clientX;
      py = e.clientY;
    };
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      camera.position.multiplyScalar(1 + Math.sign(e.deltaY) * 0.08);
      const r = camera.position.length();
      if (r < 1.6) camera.position.setLength(1.6);
      if (r > 8) camera.position.setLength(8);
    };
    renderer.domElement.addEventListener("pointerdown", onDown);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointermove", onMove);
    renderer.domElement.addEventListener("wheel", onWheel, { passive: false });

    // Pick nearest point to a click for the readout.
    const raycaster = new THREE.Raycaster();
    raycaster.params.Points = { threshold: 0.04 };
    const onClick = (e: MouseEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      const m = new THREE.Vector2(
        ((e.clientX - rect.left) / rect.width) * 2 - 1,
        -((e.clientY - rect.top) / rect.height) * 2 + 1
      );
      raycaster.setFromCamera(m, camera);
      const hits = raycaster.intersectObject(cloud);
      if (hits.length && hits[0].index != null)
        setSelected(points[hits[0].index]);
    };
    renderer.domElement.addEventListener("click", onClick);

    let raf = 0;
    const animate = () => {
      raf = requestAnimationFrame(animate);
      earthGroup.rotation.x = rot.x;
      earthGroup.rotation.y = rot.y;
      cloud.rotation.x = rot.x;
      cloud.rotation.y = rot.y;
      if (!dragging) rot.y += 0.0008;
      renderer.render(scene, camera);
    };
    animate();

    const onResize = () => {
      const w = mount.clientWidth;
      const h = mount.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    window.addEventListener("resize", onResize);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointermove", onMove);
      renderer.domElement.removeEventListener("pointerdown", onDown);
      renderer.domElement.removeEventListener("wheel", onWheel);
      renderer.domElement.removeEventListener("click", onClick);
      renderer.dispose();
      geom.dispose();
      mount.removeChild(renderer.domElement);
    };
  }, [points]);

  return (
    <div className="globe-wrap">
      <div ref={mountRef} className="globe-canvas" />
      {selected && (
        <div className="globe-readout">
          <button className="close" onClick={() => setSelected(null)}>
            ×
          </button>
          <div className="pair">
            {selected.a} × {selected.b}
          </div>
          <div className="metrics">
            <span>{selected.miss_km.toFixed(2)} km miss</span>
            <span>{selected.relv_km_s.toFixed(1)} km/s</span>
            <span>{selected.tca.slice(0, 16).replace("T", " ")} UTC</span>
          </div>
        </div>
      )}
      <div className="globe-legend">
        <span className="dot slow" /> slow approach
        <span className="dot fast" /> fast crossing
        <span className="hint">drag to rotate · scroll to zoom · click a point</span>
      </div>
    </div>
  );
}
