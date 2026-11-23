/**
 * CommentEditor - Virtual Keyboard Inset Handling and Mobile Toolbar for Ticket Comment Editor (KAN-345, S2.1).
 */

import React, { type JSX } from 'react';
import {
  CommentComposer,
  type CommentComposerProps,
} from '../activity/CommentComposer';
import './CommentEditor.css';

export type CommentEditorProps = CommentComposerProps;

export function CommentEditor(props: CommentEditorProps): JSX.Element {
  return (
    <div className="comment-editor" data-testid="comment-editor">
      <CommentComposer {...props} />
    </div>
  );
}

export default CommentEditor;
