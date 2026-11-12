/**
 * Media Story Showcase Component (KB-P3-48).
 * Mounted at /__dev/media for interactive verification of safe SVG blob rendering,
 * pan/zoom lightbox, contrast backdrop cycle, and external media shield badge.
 */

import React, { useEffect, useState, type JSX } from 'react';
import { MediaViewport } from '../editor/media/MediaViewport';
import { createSafeSvgBlobUrl } from '../editor/media/safeSvg';
import './MediaStory.css';

const SAMPLE_DARK_STROKE_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 260" width="600" height="260">
  <defs>
    <linearGradient id="g1" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#38bdf8" />
      <stop offset="100%" stop-color="#0284c7" />
    </linearGradient>
  </defs>
  <rect x="20" y="20" width="220" height="100" rx="10" fill="#f8fafc" stroke="#0f172a" stroke-width="3" />
  <text x="130" y="65" text-anchor="middle" font-family="monospace" font-size="16" font-weight="bold" fill="#0f172a">Caddy Edge Gateway</text>
  <text x="130" y="90" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#475569">Strict CSP S5.4</text>
  <path d="M 240 70 L 340 70" stroke="#0f172a" stroke-width="3" stroke-dasharray="6,4" />
  <rect x="340" y="20" width="240" height="100" rx="10" fill="url(#g1)" stroke="#0f172a" stroke-width="3" />
  <text x="460" y="65" text-anchor="middle" font-family="monospace" font-size="16" font-weight="bold" fill="#ffffff">PostgreSQL Universal Graph</text>
  <text x="460" y="90" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#f0f9ff">FORCE ROW LEVEL SECURITY</text>
  <rect x="180" y="150" width="240" height="80" rx="8" fill="#ffffff" stroke="#0f172a" stroke-width="2" />
  <text x="300" y="195" text-anchor="middle" font-family="sans-serif" font-size="14" fill="#0f172a">Safe Media Shield</text>
</svg>`;

const PROXIED_EXTERNAL_IMAGE = 'https://images.example.com/architecture-overview.png';
const AIRGAP_EXTERNAL_IMAGE = 'https://external-cdn.example.com/metrics-chart.png';

export function MediaStory(): JSX.Element {
  const [svgResult] = useState(() => createSafeSvgBlobUrl(SAMPLE_DARK_STROKE_SVG));

  useEffect(() => {
    return () => {
      if (svgResult.ok) {
        svgResult.revoke();
      }
    };
  }, [svgResult]);

  const svgBlobUrl = svgResult.ok ? svgResult.blobUrl : '';

  return (
    <div className="media-story-container" data-testid="media-story">
      <header className="media-story-header">
        <h1>Media Viewport & Safe SVG Showcase</h1>
        <p>Interactive verification for KB-P3-48 / S5.4</p>
      </header>

      <div className="media-story-grid">
        {/* Section 1: Safe SVG with Checkerboard Backdrop Toggle */}
        <section className="media-story-card" data-testid="story-section-svg">
          <h2>1. Safe SVG with Dark Strokes & Contrast Toggle</h2>
          <p>Toggles theme, light, dark, and checkerboard backdrop classes.</p>
          {svgBlobUrl && (
            <MediaViewport
              src={svgBlobUrl}
              alt="Architecture Overview Vector Diagram"
              rawSource={SAMPLE_DARK_STROKE_SVG}
              safeFilename="architecture-diagram.svg"
              testId="story-svg-viewport"
            />
          )}
        </section>

        {/* Section 2: Lightbox Pan / Zoom Showcase */}
        <section className="media-story-card" data-testid="story-section-lightbox">
          <h2>2. Media Lightbox Showcase (10% - 800% Zoom)</h2>
          <p>Click image or expand button to open full-viewport pan/zoom dialog.</p>
          {svgBlobUrl && (
            <MediaViewport
              src={svgBlobUrl}
              alt="Interactive Lightbox Asset"
              rawSource={SAMPLE_DARK_STROKE_SVG}
              testId="story-lightbox-viewport"
            />
          )}
        </section>

        {/* Section 3: Proxied External Image */}
        <section className="media-story-card" data-testid="story-section-proxied">
          <h2>3. External Media Shield Badge</h2>
          <p>Proxied anonymously via Kanban Media Shield with 🌐 badge.</p>
          <MediaViewport
            src={PROXIED_EXTERNAL_IMAGE}
            alt="External Proxied Architectural Asset"
            testId="story-proxied-viewport"
          />
        </section>

        {/* Section 4: Air-Gap Offline Placeholder */}
        <section className="media-story-card" data-testid="story-section-airgap">
          <h2>4. Air-Gap Local-Only Mode (Zero Network Calls)</h2>
          <p>Blocked with 📴 offline placeholder card when air_gap_mode is active.</p>
          <MediaViewport
            src={AIRGAP_EXTERNAL_IMAGE}
            alt="Air-gap Blocked Asset"
            airGapMode={true}
            testId="story-airgap-viewport"
          />
        </section>
      </div>
    </div>
  );
}
