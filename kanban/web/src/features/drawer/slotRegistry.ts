import type { IssueSurfaceSlots } from './slots';
import { SubscribeAction } from '../drawer-actions/SubscribeAction';
import { LinkGraphAction } from '../drawer-actions/LinkGraphAction';
import { IssueOverflowMenu } from '../drawer-actions/IssueOverflowMenu';

export const issueSurfaceSlots: IssueSurfaceSlots = {
  subscribe: SubscribeAction,
  link: LinkGraphAction,
  overflow: IssueOverflowMenu,
};
