# Visual Verification & Screenshot Annotations: KANBA-93 (KB-P3-46)

This directory contains 12 forensic visual proof screenshots captured during Playwright E2E verification of the 5-branch clipboard auto-convert paste classifier, hidden-DOM paste-jacking pruner, and sanitized status pill (`<SanitizedPastePill>`) across Desktop (1440x900), Tablet (1024x768), and Mobile (390x844). Every screenshot features crisp client-side visual annotations rendered by the annotation helper: red target bounding boxes, numeric target badges, and bottom legend strips.

## Screenshot Index & Evidence Matrix

### 01-html-paste-with-pill-{desktop, tablet, mobile}.png
- Scenario: Rich HTML paste containing 2 hidden-DOM payloads converts to clean GFM Markdown and mounts floating sanitized status pill with interactive tooltip.
- Targets:
  1. Converted GFM Table (`[data-testid="story-editor-wysiwyg"] table`) - Rich HTML converted to canonical pipe table (`Metric` | `Target` | `Latency < 1ms`).
  2. Sanitized 🧼 Pill (`[data-testid="story-editor-sanitized-pill-emoji-hint"]`) - 24x24 status pill indicating clean conversion with `Converted to Markdown` label.
  3. Paste-Jacking Defense Hint (`[data-testid="story-editor-sanitized-pill-emoji-hint-popup"]`) - Tooltip displaying `Converted pasted HTML to clean Markdown - Cmd+Z to paste plain text (stripped 2 hidden element(s))`.
- Visual Verification:
  - Both hidden elements (`<span style="display:none">hidden payload 1</span>` and `<span hidden>hidden payload 2</span>`) are completely pruned.
  - Floating pill mounts at the bottom-right slot with zero layout shift.
  - Tooltip opens cleanly showing exact hidden element count and Cmd+Z plain text hint.

### 02-cmd-z-plaintext-fallback-{desktop, tablet, mobile}.png
- Scenario: Two-step Cmd/Ctrl+Z undo contract: first undo reverts converted Markdown blocks to unformatted plain text.
- Targets:
  1. Cmd+Z Undo Trigger (`[data-testid="btn-undo"]`) - First undo operation trigger.
  2. Plain-Text Fallback (`[data-testid="story-editor-wysiwyg"]`) - Editor content reverted to raw plain text.
  3. Serialized Plain Text (`[data-testid="serialized-output"]`) - Live serialized output confirming plain-text state without Markdown table or heading markers.
- Visual Verification:
  - Heading `## Specifications` and pipe table formatting are rolled back.
  - Raw unformatted plain text (`Specifications`, `Metric | Target`, `Latency | < 1ms`) is preserved.

### 03-ide-code-paste-{desktop, tablet, mobile}.png
- Scenario: VS Code syntax-highlighted HTML and metadata paste bypasses HTML parser and emits clean fenced code block.
- Targets:
  1. IDE Code Paste Trigger (`[data-testid="btn-paste-ide-code"]`) - VS Code HTML and metadata paste trigger.
  2. Fenced Code Block (`[data-testid="story-editor-wysiwyg"] pre`) - Clean fenced ts code block with zero syntax span noise.
  3. Canonical Code Fence (`[data-testid="serialized-output"]`) - Serialized markdown with ts language identifier.
- Visual Verification:
  - All syntax-highlighting span tags, inline font-color styling, and wrapper divs are bypassed.
  - Fenced code block is cleanly rendered in the ProseMirror canvas and serialized as ```` ```ts ````.

### 04-image-paste-upload-{desktop, tablet, mobile}.png
- Scenario: Binary PNG clipboard paste inserts optimistic placeholder and resolves to attachment markdown URI.
- Targets:
  1. Binary Image Paste Trigger (`[data-testid="btn-paste-image"]`) - PNG clipboard paste trigger.
  2. Attachment Markdown URI (`[data-testid="serialized-output"]`) - Optimistic placeholder replaced with `![screen.png](attachment://att_0196ed42)`.
- Visual Verification:
  - Optimistic placeholder `[Uploading screen.png...]` inserted synchronously.
  - Async network upload succeeds against `/api/v1/projects/KAN/attachments`.
  - Placeholder is surgically replaced in-place with canonical `![screen.png](attachment://att_0196ed42)`.
