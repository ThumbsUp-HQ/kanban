import React, { type JSX } from 'react';
import {
  PriorityIcon,
  StateProgressRing,
  KANBAN_ICON_MAP,
  type KanbanIconName,
} from '../components/icons/KanbanIcons';
import { StateBadge } from '../components/state/StateBadge';
import './IconStory.css';

export function IconStory(): JSX.Element {
  const priorities = ['urgent', 'high', 'medium', 'low', 'none'] as const;
  const states = [
    { group: 'backlog', name: 'Backlog' },
    { group: 'unstarted', name: 'Todo' },
    { group: 'started', name: 'In Progress' },
    { group: 'started', name: 'In Review' },
    { group: 'completed', name: 'Done' },
    { group: 'cancelled', name: 'Cancelled' },
  ] as const;

  const sampleModules: { id: string; name: string; emoji?: string }[] = [
    { id: 'mod-1', name: 'Auth Core', emoji: '🔒' },
    { id: 'mod-2', name: 'Kanban Board', emoji: '📋' },
    { id: 'mod-3', name: 'Security Vault', emoji: '🛡️' },
    { id: 'mod-4', name: 'Custom Scripts', emoji: '🧪' },
    { id: 'mod-5', name: 'AI Interceptors', emoji: '🤖' },
  ];

  const iconNames = Object.keys(KANBAN_ICON_MAP) as KanbanIconName[];

  return (
    <div className="icon-story" data-testid="icon-story">
      <header className="icon-story-header">
        <h1>Corporate Priority Icons, Color-Coded State Badges &amp; SVG Registry</h1>
        <p>KB-UX-02 (KANBA-172): Zero-dependency ~50-icon pure SVG JSX catalog with CSP compliance.</p>
      </header>

      {/* 1. Corporate Priority Icons */}
      <section className="icon-story-section" data-testid="section-priorities">
        <h2>1. Corporate Priority Icons (Replace zzz)</h2>
        <div className="icon-story-grid">
          {priorities.map((p) => (
            <div key={p} className="icon-story-card" data-testid={`priority-card-${p}`}>
              <PriorityIcon priority={p} size={24} />
              <span className="icon-story-card-title">{p.toUpperCase()}</span>
            </div>
          ))}
        </div>
      </section>

      {/* 2. Color-Coded State Badges */}
      <section className="icon-story-section" data-testid="section-states">
        <h2>2. Color-Coded State Badges (Replace White Circle)</h2>
        <div className="icon-story-badge-row">
          {states.map((st) => (
            <StateBadge
              key={`${st.group}-${st.name}`}
              state={{ group: st.group, name: st.name }}
            />
          ))}
        </div>
        <div className="icon-story-badge-row icon-story-badge-row--spaced">
          {states.map((st) => (
            <StateBadge
              key={`compact-${st.group}-${st.name}`}
              state={{ group: st.group, name: st.name }}
              showLabel={false}
            />
          ))}
        </div>
      </section>

      {/* 3. Workflow State Progress Rings */}
      <section className="icon-story-section" data-testid="section-rings">
        <h2>3. Workflow State Progress Rings</h2>
        <div className="icon-story-grid">
          {['backlog', 'unstarted', 'started', 'in_review', 'completed', 'cancelled'].map((r) => (
            <div key={r} className="icon-story-card" data-testid={`ring-card-${r}`}>
              <StateProgressRing state={r} size={24} />
              <span className="icon-story-card-title">{r}</span>
            </div>
          ))}
        </div>
      </section>

      {/* 4. Arbitrary Module Emojis */}
      <section className="icon-story-section" data-testid="section-modules">
        <h2>4. Arbitrary Module Emojis</h2>
        <div className="icon-story-badge-row">
          {sampleModules.map((m) => (
            <span key={m.id} className="icon-story-module-chip">
              <span>{m.emoji ?? '🧩'}</span>
              <span>{m.name}</span>
            </span>
          ))}
        </div>
      </section>

      {/* 5. Curated Zero-Dependency SVG Registry (~50 icons) */}
      <section className="icon-story-section" data-testid="section-svg-registry">
        <h2>5. Zero-Dependency SVG Icon Registry ({iconNames.length} Icons)</h2>
        <div className="icon-story-grid">
          {iconNames.map((name) => {
            const IconComp = KANBAN_ICON_MAP[name];
            return (
              <div key={name} className="icon-story-card" data-testid={`svg-card-${name}`}>
                <IconComp size={22} />
                <span className="icon-story-card-title">{name}</span>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
