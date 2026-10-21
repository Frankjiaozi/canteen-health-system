import type { ReactNode } from 'react';
import SpotlightCard from './react-bits/SpotlightCard';

export function SoftCard({
  children,
  className = '',
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <SpotlightCard
      className={`zw-soft-card ${className}`}
      theme="light"
      spotlightColor="#789074"
      intensity={0.24}
      borderGlow={0.2}
      proximity={0}
      flare={false}
    >
      {children}
    </SpotlightCard>
  );
}
