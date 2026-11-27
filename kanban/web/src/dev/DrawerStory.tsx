import React, { useState, type JSX } from 'react';
import { IssueKeyLink } from '../features/drawer/IssueKeyLink';
import { ManageAccessModal } from '../features/access/ManageAccessModal';
import './DrawerStory.css';

export function DrawerStory(): JSX.Element {
  const [manageAccessOpen, setManageAccessOpen] = useState(
    typeof window !== 'undefined' &&
      new URLSearchParams(window.location.search).get('modal') === 'access',
  );

  return (
    <main id="kb-main" tabIndex={-1} data-testid="drawer-story" className="drawer-story">
      <h1>Ticket Drawer Story</h1>
      <p>Test fixture links for drawer verification across viewports.</p>
      <button
        type="button"
        data-testid="open-manage-access-btn"
        onClick={() => { setManageAccessOpen(true); }}
      >
        Open Manage Access Modal
      </button>
      <ul className="drawer-story__list">
        <li className="drawer-story__item">
          <IssueKeyLink
            issueKey="KAN-142"
            className="drawer-story__link"
            data-testid="link-kan-142"
          >
            Open KAN-142 (Auth Studio)
          </IssueKeyLink>
        </li>
        <li className="drawer-story__item">
          <IssueKeyLink
            issueKey="KAN-143"
            className="drawer-story__link"
            data-testid="link-kan-143"
          >
            Open KAN-143 (Next Task)
          </IssueKeyLink>
        </li>
        <li className="drawer-story__item">
          <IssueKeyLink
            issueKey="KAN-999"
            className="drawer-story__link"
            data-testid="link-kan-999"
          >
            Open KAN-999 (Not Found)
          </IssueKeyLink>
        </li>
      </ul>
      <ManageAccessModal
        objectId="c0000000-0000-0000-0000-000000000142"
        canonicalKey="KAN-142"
        isOpen={manageAccessOpen}
        onClose={() => { setManageAccessOpen(false); }}
      />
    </main>
  );
}
