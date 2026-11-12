import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen, act } from '@testing-library/react';
import { EmojiStory } from './EmojiStory';
import { EMOJI_REGISTRY } from '../components/emoji/emojiRegistry';

describe('EmojiStory Component', () => {
  it('renders the gallery with all 21 emoji cards', () => {
    render(<EmojiStory />);

    expect(screen.getByTestId('emoji-story')).toBeDefined();
    expect(screen.getByTestId('emoji-grid')).toBeDefined();

    for (const key of Object.keys(EMOJI_REGISTRY)) {
      expect(screen.getByTestId(`card-${key}`)).toBeDefined();
      expect(screen.getByTestId(`hint-${key}`)).toBeDefined();
    }
  });

  it('renders custom rich content for access, gateApproved, priorityUrgent, and externalAssignee', () => {
    render(<EmojiStory />);

    // Access trigger focus
    const accessTrigger = screen.getByTestId('hint-access');
    act(() => {
      fireEvent.focus(accessTrigger);
    });
    const accessPopup = screen.getByTestId('hint-access-popup');
    expect(accessPopup.textContent).toContain('Project: Platform Core');
    expect(accessPopup.textContent).toContain('14 users, 2 groups, 2 🤖 agents, 1 🔒 deny rule');

    // GateApproved trigger focus
    const gateTrigger = screen.getByTestId('hint-gateApproved');
    act(() => {
      fireEvent.focus(gateTrigger);
    });
    const gatePopup = screen.getByTestId('hint-gateApproved-popup');
    expect(gatePopup.textContent).toContain('Gate sec-review (cli: agy -p) approved in 812ms');
    expect(screen.getByTestId('verdict-hash').textContent).toContain('9f2c83d4e1b5a2f679e01234abcd5678ef90123456789abcdef012345678e41a');

    // PriorityUrgent trigger focus
    const priorityTrigger = screen.getByTestId('hint-priorityUrgent');
    act(() => {
      fireEvent.focus(priorityTrigger);
    });
    const priorityPopup = screen.getByTestId('hint-priorityUrgent-popup');
    expect(priorityPopup.textContent).toContain('Urgent - SLA 4h - sort weight 1 - press P to change');

    // ExternalAssignee trigger focus
    const assigneeTrigger = screen.getByTestId('hint-externalAssignee');
    act(() => {
      fireEvent.focus(assigneeTrigger);
    });
    const assigneePopup = screen.getByTestId('hint-externalAssignee-popup');
    expect(assigneePopup.textContent).toContain('External free-text label - grants zero access and sends zero notifications');
  });

  it('interactive sample opens dialog and action logs inspector-opened', () => {
    render(<EmojiStory />);

    const logEl = screen.getByTestId('activation-log');
    expect(logEl.textContent).toBe('idle');

    const trigger = screen.getByTestId('interactive-hint');
    act(() => {
      fireEvent.focus(trigger);
    });

    const actionBtn = screen.getByTestId('interactive-hint-action-btn');
    expect(actionBtn.textContent).toBe('Open Access Inspector');

    act(() => {
      fireEvent.click(actionBtn);
    });

    expect(logEl.textContent).toBe('inspector-opened');
  });

  it('renders edge flip sample trigger', () => {
    render(<EmojiStory />);
    expect(screen.getByTestId('edge-hint-trigger')).toBeDefined();
  });
});
