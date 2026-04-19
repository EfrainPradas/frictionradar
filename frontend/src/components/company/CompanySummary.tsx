import type { Company } from '../../types/company';

interface Props {
  company: Company;
}

export function CompanySummary({ company }: Props) {
  const fields = [
    { label: 'Domain', value: company.domain },
    { label: 'Industry', value: company.industry },
    { label: 'Company Size', value: company.company_size },
    { label: 'Source Added From', value: company.source_added_from },
    {
      label: 'Added',
      value: new Date(company.created_at).toLocaleDateString(),
    },
  ];

  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3">
      {fields.map((f) => (
        <div key={f.label}>
          <dt className="text-xs font-medium text-gray-400 uppercase tracking-wide">
            {f.label}
          </dt>
          <dd className="mt-0.5 text-sm text-gray-900">
            {f.value ?? <span className="text-gray-400">—</span>}
          </dd>
        </div>
      ))}
    </dl>
  );
}
