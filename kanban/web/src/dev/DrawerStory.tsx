import React, { type JSX } from 'react';
import { IssueKeyLink } from '../features/drawer/IssueKeyLink';
import './DrawerStory.css';

export function DrawerStory(): JSX.Element {
  return (
    <main id="kb-main" tabIndex={-1} data-testid="drawer-story" className="drawer-story">
      <h1>Ticket Drawer Story</h1>
      <p>Test fixture links for drawer verification across viewports.</p>
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
    </main>
  );
}
