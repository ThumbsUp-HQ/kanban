/**
 * ProseMirror sourceSlice Dirty Tracking Plugin (KB-P3-45, S5.2 item 5).
 * Monitors transaction StepMaps and marks touched top-level blocks dirty: true while
 * preserving byte-exact sourceSlice { from, to } metadata on untouched blocks.
 */

import { Plugin, PluginKey, type Transaction } from 'prosemirror-state';

export const sourceSlicePluginKey = new PluginKey('sourceSlicePlugin');

export function createSourceSlicePlugin(): Plugin {
  return new Plugin({
    key: sourceSlicePluginKey,

    appendTransaction(transactions, _oldState, newState) {
      const docChanged = transactions.some((tr) => tr.docChanged);
      if (!docChanged) {
        return null;
      }

      // Allow programmatic operations (initial load, raw toggle reset) to bypass dirty marking
      if (transactions.some((tr) => tr.getMeta('skipSourceSliceDirty'))) {
        return null;
      }

      // Collect all modified ranges in newState.doc coordinates
      const changedRanges: { from: number; to: number }[] = [];

      for (const tr of transactions) {
        if (!tr.docChanged) continue;
        for (const step of tr.steps) {
          const map = step.getMap();
          map.forEach((_oldStart, _oldEnd, newStart, newEnd) => {
            changedRanges.push({ from: newStart, to: newEnd });
          });
        }
      }

      if (changedRanges.length === 0) {
        return null;
      }

      // Identify which top-level children in newState.doc overlap with any changed range
      const touchedIndices = new Set<number>();
      let pos = 0;

      for (let i = 0; i < newState.doc.childCount; i++) {
        const child = newState.doc.child(i);
        const childStart = pos;
        const childEnd = pos + child.nodeSize;
        pos = childEnd;

        for (const range of changedRanges) {
          // If range is an insertion point (from === to), check if it lies inside or at boundary
          const overlaps =
            range.from === range.to
              ? range.from >= childStart && range.from <= childEnd
              : range.from < childEnd && range.to > childStart;

          if (overlaps) {
            touchedIndices.add(i);
          }
        }
      }

      if (touchedIndices.size === 0) {
        return null;
      }

      // Build appendTransaction setting dirty: true and sourceSlice: null on touched blocks
      let tr: Transaction | null = null;
      let checkPos = 0;

      for (let i = 0; i < newState.doc.childCount; i++) {
        const child = newState.doc.child(i);
        const childStart = checkPos;
        checkPos += child.nodeSize;

        if (touchedIndices.has(i)) {
          const isAlreadyDirty = Boolean(child.attrs.dirty) && child.attrs.sourceSlice === null;
          if (!isAlreadyDirty) {
            tr ??= newState.tr.setMeta('skipSourceSliceDirty', true);
            tr.setNodeMarkup(childStart, undefined, {
              ...child.attrs,
              sourceSlice: null,
              dirty: true,
            });
          }
        }
      }

      return tr;
    },
  });
}
