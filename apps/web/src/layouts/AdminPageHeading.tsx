import type { ReactNode } from 'react';

export function AdminPageHeading({
  title,
  tag,
  tagline,
}: {
  title: string;
  tag?: ReactNode;
  tagline?: string;
}) {
  return (
    <div className="zw-admin-page-heading">
      <span className="zw-admin-page-mark" aria-hidden="true" />
      <h1 className="zw-admin-page-title">{title}</h1>
      {tag}
      {tagline && <span className="zw-admin-page-tagline">{tagline}</span>}
    </div>
  );
}
