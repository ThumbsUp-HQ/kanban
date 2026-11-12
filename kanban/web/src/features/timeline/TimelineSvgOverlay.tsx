import React, { type JSX } from 'react';
import type { BlocksArrowPath } from './timelineGeometry';

export interface TimelineSvgOverlayProps {
  arrows: BlocksArrowPath[];
  totalWidth: number;
  totalHeight: number;
  visible?: boolean;
}

/**
 * Pure SVG layer rendering orthogonal cubic-bezier BLOCKS dependency arrows (KB-P3-39, S6.4 item 2).
 * Strictly zero inline style attributes (preserves Content Security Policy style-src 'self').
 */
export function TimelineSvgOverlay({
  arrows,
  totalWidth,
  totalHeight,
  visible = true,
}: TimelineSvgOverlayProps): JSX.Element | null {
  if (!visible || arrows.length === 0) {
    return null;
  }

  return (
    <svg
      className="timeline-svg-overlay"
      data-testid="timeline-svg-overlay"
      width={totalWidth}
      height={totalHeight}
      aria-hidden="true"
    >
      <defs>
        <marker
          id="timeline-arrowhead"
          markerWidth={6}
          markerHeight={6}
          refX={5}
          refY={3}
          orient="auto"
          markerUnits="strokeWidth"
        >
          <path d="M 0 0 L 6 3 L 0 6 z" className="timeline-arrowhead-path" />
        </marker>
        <marker
          id="timeline-arrowhead-conflict"
          markerWidth={6}
          markerHeight={6}
          refX={5}
          refY={3}
          orient="auto"
          markerUnits="strokeWidth"
        >
          <path d="M 0 0 L 6 3 L 0 6 z" className="timeline-arrowhead-path--conflict" />
        </marker>
      </defs>
      <g className="timeline-arrows-group">
        {arrows.map((arrow) => {
          const arrowClasses = [
            'gantt-arrow',
            arrow.isConflict ? 'gantt-arrow--conflict' : '',
          ]
            .filter(Boolean)
            .join(' ');

          const markerUrl = arrow.isConflict
            ? 'url(#timeline-arrowhead-conflict)'
            : 'url(#timeline-arrowhead)';

          return (
            <path
              key={`${arrow.sourceKey}->${arrow.targetKey}`}
              d={arrow.d}
              className={arrowClasses}
              markerEnd={markerUrl}
              fill="none"
              strokeWidth={2}
              data-source-key={arrow.sourceKey}
              data-target-key={arrow.targetKey}
              data-conflict={arrow.isConflict ? 'true' : undefined}
            />
          );
        })}
      </g>
    </svg>
  );
}
