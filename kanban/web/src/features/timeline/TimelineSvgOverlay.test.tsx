import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';
import { TimelineSvgOverlay } from './TimelineSvgOverlay';
import type { BlocksArrowPath } from './timelineGeometry';

describe('TimelineSvgOverlay', () => {
  const arrows: BlocksArrowPath[] = [
    {
      sourceKey: 'KAN-100',
      targetKey: 'KAN-142',
      d: 'M 100 20 L 200 40',
      isConflict: false,
      isBrokenLink: false,
      isRestricted: false,
    },
    {
      sourceKey: 'KAN-142',
      targetKey: 'KAN-143',
      d: 'M 200 40 L 300 60',
      isConflict: true,
      isBrokenLink: true,
      isRestricted: false,
    },
  ];

  it('renders SVG overlay with arrows and conflict markers', () => {
    const { container } = render(
      <TimelineSvgOverlay
        arrows={arrows}
        totalWidth={800}
        totalHeight={400}
        visible={true}
      />
    );

    const svg = container.querySelector('svg');
    expect(svg).not.toBeNull();
    expect(svg?.getAttribute('width')).toBe('800');
    expect(svg?.getAttribute('height')).toBe('400');

    const paths = container.querySelectorAll('.gantt-arrow');
    expect(paths.length).toBe(2);

    const conflict = container.querySelector('.gantt-arrow--conflict');
    expect(conflict).not.toBeNull();
  });

  it('returns null when visible is false or arrows are empty', () => {
    const { container: c1 } = render(
      <TimelineSvgOverlay
        arrows={arrows}
        totalWidth={800}
        totalHeight={400}
        visible={false}
      />
    );
    expect(c1.querySelector('svg')).toBeNull();

    const { container: c2 } = render(
      <TimelineSvgOverlay
        arrows={[]}
        totalWidth={800}
        totalHeight={400}
        visible={true}
      />
    );
    expect(c2.querySelector('svg')).toBeNull();
  });
});
