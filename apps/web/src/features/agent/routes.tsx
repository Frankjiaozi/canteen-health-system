import { lazy } from 'react';

export const AgentPage = lazy(() =>
  import('./AgentPage').then((module) => ({ default: module.AgentPage })),
);
