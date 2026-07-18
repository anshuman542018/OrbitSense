import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "OrbitSense — a copilot for everything happening in Earth orbit",
  description:
    "OrbitSense ingests the public satellite catalog daily, screens for close approaches, detects maneuvers, and explains each event in plain language with the numbers to back it up.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <header className="masthead">
          <div className="wrap">
            <div className="brand">
              <h1>◍ OrbitSense</h1>
              <span className="tag">space domain awareness copilot</span>
            </div>
            <nav className="nav">
              <a href="/">Feed</a>
              <a href="/globe">3D Globe</a>
              <a href="/chat">Chat</a>
              <a
                href="https://github.com/OWNER/orbitsense"
                target="_blank"
                rel="noreferrer"
              >
                GitHub
              </a>
            </nav>
          </div>
        </header>
        {children}
      </body>
    </html>
  );
}
