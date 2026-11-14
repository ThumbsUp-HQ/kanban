import { useState, type JSX } from 'react';
import { PropertiesRail } from '../features/drawer-rail/PropertiesRail';
import type { IssueDetail } from '../features/drawer/slots';
import type { ProjectMetadata } from '../features/drawer-rail/railApi';
import defaultIssueJson from '../../e2e/fixtures/issue-kan-142-detail.json';
import restrictedParentJson from '../../e2e/fixtures/issue-kan-restricted-parent.json';
import noModulesProjectJson from '../../e2e/fixtures/project-kan-nomodules.json';
import './RailStory.css';

const defaultIssue = defaultIssueJson as unknown as IssueDetail;
const restrictedParentIssue = restrictedParentJson as unknown as IssueDetail;
const noModulesProject = noModulesProjectJson as unknown as ProjectMetadata;

export function RailStory(): JSX.Element {
  const [selectedFixture, setSelectedFixture] = useState<'default' | 'nomodules' | 'restricted'>('default');

  let activeIssue: IssueDetail = defaultIssue;
  let activeMeta: ProjectMetadata | undefined = undefined;

  if (selectedFixture === 'nomodules') {
    activeIssue = defaultIssue;
    activeMeta = noModulesProject;
  } else if (selectedFixture === 'restricted') {
    activeIssue = restrictedParentIssue;
  }

  return (
    <div className="rail-story" data-testid="rail-story">
      <header className="rail-story__header">
        <h2 className="rail-story__title">Properties Rail Dev Story</h2>
        <div className="rail-story__controls">
          <button
            type="button"
            className="creator-row__change-btn"
            onClick={() => { setSelectedFixture('default'); }}
          >
            All Properties (KAN-142)
          </button>
          <button
            type="button"
            className="creator-row__change-btn"
            onClick={() => { setSelectedFixture('nomodules'); }}
          >
            No Modules (Unmounted)
          </button>
          <button
            type="button"
            className="creator-row__change-btn"
            onClick={() => { setSelectedFixture('restricted'); }}
          >
            Restricted Parent (Masked)
          </button>
        </div>
      </header>

      <main className="rail-story__main">
        <div className="rail-story__rail-container">
          <PropertiesRail
            key={selectedFixture}
            issue={activeIssue}
            projectMetadata={activeMeta}
          />
        </div>
      </main>
    </div>
  );
}
