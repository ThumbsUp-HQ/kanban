import type { IssueSurfaceSlots } from './slots';
import { PropertiesRail } from '../drawer-rail/PropertiesRail';
import { SubscribeAction } from '../drawer-actions/SubscribeAction';
import { LinkGraphAction } from '../drawer-actions/LinkGraphAction';
import { IssueOverflowMenu } from '../drawer-actions/IssueOverflowMenu';
import { ActivitySection } from '../activity/ActivitySection';

export const issueSurfaceSlots: IssueSurfaceSlots = {
  rail: PropertiesRail,
  subscribe: SubscribeAction,
  link: LinkGraphAction,
  overflow: IssueOverflowMenu,
  activity: ActivitySection,
};
