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
      <div className="zw-admin-page-heading-copy">
        <div className="zw-admin-page-title-row">
          <h1 className="zw-admin-page-title">{title}</h1>
          {tag}
        </div>
        {tagline && <p className="zw-admin-page-tagline">{tagline}</p>}
      </div>
    </div>
  );
}
