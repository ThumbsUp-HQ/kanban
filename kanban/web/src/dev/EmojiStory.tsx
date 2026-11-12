import React, { useState, type JSX } from 'react';
import { EmojiHint } from '../components/emoji/EmojiHint';
import {
  EMOJI_REGISTRY,
  type EmojiKey,
} from '../components/emoji/emojiRegistry';
import './EmojiStory.css';

/**
 * Visual Gallery for testing all 21 semantic status emojis,
 * timing interactions, accessibility, and edge placement (KB-P3-31).
 */
export function EmojiStory(): JSX.Element {
  const [activationLog, setActivationLog] = useState<string>('idle');

  const orderedKeys = Object.keys(EMOJI_REGISTRY) as EmojiKey[];

  const getCustomContent = (key: EmojiKey): React.ReactNode => {
    if (key === 'access') {
      return (
        <div>
          <div>
            <strong>Project: Platform Core</strong>
          </div>
          <div>14 users, 2 groups, 2 🤖 agents, 1 🔒 deny rule</div>
          <div>Click to open Access Inspector</div>
        </div>
      );
    }

    if (key === 'gateApproved') {
      return (
        <div>
          <div>Gate sec-review (cli: agy -p) approved in 812ms</div>
          <div>
            verdict sha256:{' '}
            <code data-testid="verdict-hash" className="mono">
              9f2c83d4e1b5a2f679e01234abcd5678ef90123456789abcdef012345678e41a
            </code>
          </div>
        </div>
      );
    }

    if (key === 'priorityUrgent') {
      return 'Urgent - SLA 4h - sort weight 1 - press P to change';
    }

    if (key === 'externalAssignee') {
      return 'External free-text label - grants zero access and sends zero notifications';
    }

    return EMOJI_REGISTRY[key].defaultHint;
  };

  return (
    <div className="emoji-story" data-testid="emoji-story">
      <header className="emoji-story-header">
        <div>
          <h1>Semantic &lt;EmojiHint&gt; Registry Story</h1>
          <p className="emoji-story-subtitle">
            Crisp 24x24 status pills with 180ms hover delay, 0ms neighbor warmup, instant focus, and copyable popovers.
          </p>
        </div>
      </header>

      {/* 21-Emoji Registry Grid */}
      <section className="emoji-story-section" data-testid="registry-grid-section">
        <h2>21-Emoji Standardized Platform Vocabulary (S6.2)</h2>
        <div className="emoji-grid" data-testid="emoji-grid">
          {orderedKeys.map((key) => {
            const entry = EMOJI_REGISTRY[key];
            return (
              <div
                key={key}
                className="emoji-card"
                data-testid={`card-${key}`}
              >
                <div className="emoji-card-header">
                  <EmojiHint
                    kind={key}
                    testId={`hint-${key}`}
                    content={getCustomContent(key)}
                  />
                  <div>
                    <div className="emoji-card-key">{key}</div>
                    <div className="emoji-card-domain">{entry.domain}</div>
                  </div>
                </div>
                <div className="emoji-card-body">{entry.ariaLabel}</div>
              </div>
            );
          })}
        </div>
      </section>

      {/* Interactive Access Sample */}
      <section className="emoji-story-section" data-testid="interactive-section">
        <h2>Interactive Access Inspector Sample</h2>
        <div className="interactive-sample-container">
          <EmojiHint
            kind="access"
            variant="interactive"
            testId="interactive-hint"
            label="Access Inspector"
            activateLabel="Open Access Inspector"
            onActivate={() => {
              setActivationLog('inspector-opened');
            }}
            content={
              <div>
                <div>
                  <strong>Project: Platform Core</strong>
                </div>
                <div>14 users, 2 groups, 2 🤖 agents, 1 🔒 deny rule</div>
              </div>
            }
          />
          <div data-testid="activation-log" className="activation-log">
            {activationLog}
          </div>
        </div>
      </section>

      {/* Edge Flip Placement Section */}
      <section className="emoji-story-section edge-flip-section" data-testid="edge-flip-section">
        <h2>Edge Flip Placement (Clamped &amp; Flipped)</h2>
        <div className="edge-flip-box">
          <EmojiHint
            kind="warning"
            testId="edge-hint-trigger"
            label="WIP Warning at Edge"
            content="Standalone docker run mode details and volume persistence status"
          />
        </div>
      </section>
    </div>
  );
}
