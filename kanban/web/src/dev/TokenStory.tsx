import React, { useRef } from 'react';
import { useTheme, type Theme } from '../theme/ThemeProvider';
import './TokenStory.css';

export const S61_TOKENS = [
  { name: '--font-sans', raw: "'Inter Variable', -apple-system, BlinkMacSystemFont, sans-serif" },
  { name: '--font-mono', raw: "'JetBrains Mono Variable', ui-monospace, monospace" },
  { name: '--text-body', raw: '0.9375rem' },
  { name: '--leading-prose', raw: '1.73' },
  { name: '--sidebar-w', raw: '256px' },
  { name: '--topbar-h', raw: '52px' },
  { name: '--board-canvas-pad', raw: '24px 28px' },
  { name: '--board-col-w', raw: '324px' },
  { name: '--board-col-gap', raw: '20px' },
  { name: '--card-pad', raw: '16px 18px' },
  { name: '--card-gap', raw: '12px' },
  { name: '--list-row-h', raw: '46px' },
  { name: '--drawer-w', raw: 'min(960px, 68vw)' },
  { name: '--prose-pad', raw: '32px 40px' },
  { name: '--prop-row-h', raw: '38px' },
  { name: '--section-gap', raw: '32px' },
] as const;

export const SEMANTIC_COLORS = [
  { varName: '--fg-primary', label: 'Primary Text', ratioDesc: '>= 7:1' },
  { varName: '--fg-secondary', label: 'Secondary Text', ratioDesc: '>= 4.5:1' },
  { varName: '--fg-muted', label: 'Muted Text', ratioDesc: '>= 4.5:1' },
  { varName: '--accent-primary', label: 'Accent Primary', ratioDesc: '>= 4.5:1' },
  { varName: '--accent-primary-fg', label: 'Accent Primary FG', ratioDesc: '' },
  { varName: '--bg-canvas', label: 'Canvas Background', ratioDesc: '' },
  { varName: '--bg-surface', label: 'Surface Background', ratioDesc: '' },
  { varName: '--bg-surface-raised', label: 'Raised Surface', ratioDesc: '' },
  { varName: '--bg-hover', label: 'Hover Background', ratioDesc: '' },
  { varName: '--border-subtle', label: 'Subtle Border', ratioDesc: '' },
  { varName: '--border-strong', label: 'Strong Border', ratioDesc: '' },
  { varName: '--focus-ring', label: 'Focus Ring', ratioDesc: '' },
  { varName: '--warn-bg', label: 'Warning BG', ratioDesc: '' },
  { varName: '--warn-fg', label: 'Warning FG', ratioDesc: '>= 4.5:1' },
  { varName: '--danger-bg', label: 'Danger BG', ratioDesc: '' },
  { varName: '--danger-fg', label: 'Danger FG', ratioDesc: '>= 4.5:1' },
  { varName: '--ok-fg', label: 'OK FG', ratioDesc: '' },
] as const;

export const STICKY_COLORS = [
  { varName: '--sticky-amber', name: 'Amber' },
  { varName: '--sticky-mint', name: 'Mint' },
  { varName: '--sticky-sky', name: 'Sky' },
  { varName: '--sticky-lavender', name: 'Lavender' },
  { varName: '--sticky-coral', name: 'Coral' },
  { varName: '--sticky-slate', name: 'Slate' },
] as const;

const THEME_OPTIONS: Theme[] = ['light', 'dark', 'system'];

function getComputedTokenMap(): Record<string, string> {
  const computed = window.getComputedStyle(document.documentElement);
  const map: Record<string, string> = {};
  for (const t of S61_TOKENS) {
    const val = computed.getPropertyValue(t.name).trim();
    map[t.name] = val.length > 0 ? val : t.raw;
  }
  return map;
}

/**
 * Visual Token Story Component rendering the S6.1 token table,
 * spacing ruler, semantic color swatches, and accessible theme switcher.
 */
export function TokenStory(): React.JSX.Element {
  const { theme, setTheme } = useTheme();
  const computedTokens = getComputedTokenMap();
  const optionRefs = useRef<Record<Theme, HTMLButtonElement | null>>({
    light: null,
    dark: null,
    system: null,
  });

  const handleKeyDown = (e: React.KeyboardEvent, currentOpt: Theme): void => {
    let nextOpt: Theme;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      e.preventDefault();
      nextOpt = currentOpt === 'light' ? 'dark' : currentOpt === 'dark' ? 'system' : 'light';
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault();
      nextOpt = currentOpt === 'system' ? 'dark' : currentOpt === 'dark' ? 'light' : 'system';
    } else {
      return;
    }

    setTheme(nextOpt);
    optionRefs.current[nextOpt]?.focus();
  };

  return (
    <div className="token-story" data-testid="token-story">
      {/* Header and Accessible Theme Switcher */}
      <header className="token-story-header">
        <div>
          <h1>Design Tokens & Spacing Story</h1>
          <p className="typography-prose">
            Canonical S6.1 spatial whitespace tokens, semantic colors, and variable typography.
          </p>
        </div>
        <div
          role="radiogroup"
          aria-label="Theme selector"
          className="theme-radiogroup"
          data-testid="theme-radiogroup"
        >
          {THEME_OPTIONS.map((opt) => {
            const isChecked = theme === opt;
            return (
              <button
                key={opt}
                ref={(el) => {
                  optionRefs.current[opt] = el;
                }}
                type="button"
                role="radio"
                aria-checked={isChecked}
                tabIndex={isChecked ? 0 : -1}
                className="theme-radio-btn"
                data-testid={`theme-option-${opt}`}
                onClick={() => {
                  setTheme(opt);
                }}
                onKeyDown={(e) => {
                  handleKeyDown(e, opt);
                }}
              >
                {opt.charAt(0).toUpperCase() + opt.slice(1)}
              </button>
            );
          })}
        </div>
      </header>

      {/* (a) S6.1 Tokens Table */}
      <section className="token-section">
        <h2>1. S6.1 Canonical Tokens Table</h2>
        <table className="token-table" data-testid="token-table">
          <thead>
            <tr data-testid="token-table-header">
              <th>Token Name</th>
              <th>Declared S6.1 Value</th>
              <th>Computed Value</th>
            </tr>
          </thead>
          <tbody>
            {S61_TOKENS.map((token) => (
              <tr key={token.name} data-testid={`token-row-${token.name}`}>
                <td>
                  <code>{token.name}</code>
                </td>
                <td>{token.raw}</td>
                <td>
                  <code>{computedTokens[token.name]}</code>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {/* (b) Spacing Ruler */}
      <section className="token-section" data-testid="spacing-ruler">
        <h2>2. Spacing Ruler & Layout Components</h2>
        <p className="typography-prose">
          Visual validation of generous card padding, column widths, gutters, and row heights.
        </p>

        {/* Sample Card */}
        <div className="ruler-sample-card" data-testid="ruler-sample-card">
          <div style={{ fontWeight: 600, marginBottom: '8px' }}>Sample Card (--card-pad)</div>
          <div>Padding: 16px vertical, 18px horizontal</div>
        </div>

        {/* Stacked Cards with Gap */}
        <div className="ruler-card-gap-container" data-testid="ruler-card-gap-container">
          <div className="ruler-sample-card">Card A (Separated by --card-gap: 12px)</div>
          <div className="ruler-sample-card">Card B (Separated by --card-gap: 12px)</div>
        </div>

        {/* Lanes with Gutter */}
        <div className="ruler-lane-container" data-testid="ruler-lane-container">
          <div className="ruler-lane" data-testid="ruler-lane-1">
            <div style={{ fontWeight: 600 }}>Lane 1 (--board-col-w: 324px)</div>
            <p style={{ fontSize: '0.875rem' }}>Gutter to Lane 2 is --board-col-gap: 20px.</p>
          </div>
          <div className="ruler-lane" data-testid="ruler-lane-2">
            <div style={{ fontWeight: 600 }}>Lane 2 (--board-col-w: 324px)</div>
            <p style={{ fontSize: '0.875rem' }}>Spacious column width ensures breathable cards.</p>
          </div>
        </div>

        {/* List Row & Property Row */}
        <div style={{ marginTop: '20px' }}>
          <div className="ruler-list-row" data-testid="ruler-list-row">
            List Row Height (--list-row-h: 46px)
          </div>
          <div className="ruler-prop-row" data-testid="ruler-prop-row">
            Property Row Height (--prop-row-h: 38px)
          </div>
        </div>
      </section>

      {/* (c) Semantic Swatches & Contrast */}
      <section className="token-section" data-testid="color-swatches">
        <h2>3. Semantic Palette & Contrast Ratios</h2>

        <h3 style={{ marginTop: '12px', marginBottom: '8px' }}>6 Sticky Palette Colors (S8.1)</h3>
        <div className="sticky-swatches-container" data-testid="sticky-swatches-container">
          {STICKY_COLORS.map((sticky) => (
            <div
              key={sticky.varName}
              className="sticky-swatch-item"
              style={{ backgroundColor: `var(${sticky.varName})` }}
            >
              <div style={{ fontWeight: 600, color: 'var(--fg-primary)' }}>{sticky.name}</div>
              <code style={{ fontSize: '0.625rem', color: 'var(--fg-secondary)' }}>
                {sticky.varName}
              </code>
            </div>
          ))}
        </div>

        <h3 style={{ marginTop: '16px', marginBottom: '8px' }}>Semantic Theme Colors</h3>
        <div className="swatches-grid" data-testid="semantic-swatches-container">
          {SEMANTIC_COLORS.map((col) => (
            <div
              key={col.varName}
              className="swatch-card"
              data-testid={`swatch-${col.varName}`}
            >
              <div
                className="swatch-preview"
                style={{ backgroundColor: `var(${col.varName})` }}
              />
              <div className="swatch-info">
                <div>
                  <code>{col.varName}</code>
                </div>
                <div style={{ color: 'var(--fg-secondary)', fontSize: '0.75rem' }}>
                  {col.label} {col.ratioDesc && `(${col.ratioDesc})`}
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* (d) & (e) Typography: Prose and Mono Key */}
      <section className="token-section">
        <h2>4. Base Typography & Tabular Numerals</h2>
        <p className="typography-prose" data-testid="typography-prose">
          The Kanban platform pairs generous whitespace with technical prose readability.
          Body text defaults to 15px with a 26px line height, providing editorial breathing room
          while issue keys like <span className="typography-mono-key" data-testid="typography-mono-key">KAN-142</span> use JetBrains Mono tabular numerals.
        </p>
      </section>
    </div>
  );
}
