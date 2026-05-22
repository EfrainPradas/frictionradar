import { Link, useLocation, useParams } from 'react-router-dom';
import { SECTORS } from '../../../data/taxonomy';
import { getSectorAggregate } from '../../../data/mockSector';

function labelFor(slug: string): string {
  return SECTORS.find((s) => s.slug === slug)?.label ?? slug;
}

export function BreadcrumbNavigation() {
  const location = useLocation();
  const params = useParams();
  const segments = location.pathname.split('/').filter(Boolean);

  if (segments[0] !== 'markets') {
    return (
      <div className="text-[14px] font-semibold text-fr-ink capitalize">
        {segments[0] ?? 'Home'}
      </div>
    );
  }

  const crumbs: { label: string; to: string }[] = [{ label: 'Markets', to: '/markets' }];
  const isCompanyRoute = segments[2] === 'c';

  if (params.sector) {
    crumbs.push({
      label: labelFor(params.sector),
      to: `/markets/${params.sector}`,
    });

    if (isCompanyRoute && params.companyId) {
      const sector = getSectorAggregate(params.sector);
      const company = sector?.companies.find((c) => c.id === params.companyId);
      crumbs.push({
        label: company?.name ?? 'Company',
        to: location.pathname,
      });
    }
  }

  return (
    <nav className="flex items-center gap-2 text-[13px] min-w-0">
      {crumbs.map((c, i) => {
        const isLast = i === crumbs.length - 1;
        return (
          <span key={`${c.to}-${i}`} className="flex items-center gap-2 min-w-0">
            {i > 0 && <span className="text-fr-ink-faint">/</span>}
            {isLast ? (
              <span className="text-fr-ink font-semibold truncate">{c.label}</span>
            ) : (
              <Link to={c.to} className="text-fr-ink-mute hover:text-fr-ink transition-colors truncate">
                {c.label}
              </Link>
            )}
          </span>
        );
      })}
    </nav>
  );
}
