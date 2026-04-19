import { AppLayout } from '../components/layout/AppLayout';

const BACKEND_BASE = (import.meta.env.VITE_API_URL || 'http://localhost:50000/api/v1')
  .replace(/\/api\/v1\/?$/, '');

const HEATMAP_URL = `${BACKEND_BASE}/heatmap`;

export function HeatmapPage() {
  return (
    <AppLayout
      title="Mapa de fricción"
      subtitle="Sector × función · índice de dolor compuesto"
    >
      <div className="flex flex-col h-full gap-3">
        <div className="flex items-center justify-between px-1">
          <p className="text-xs text-gray-500">
            Generado desde <code className="text-gray-700">scripts/gen_friction_heatmap.py</code>.
            Pasa el mouse sobre una celda para ver las empresas.
          </p>
          <a
            href={HEATMAP_URL}
            target="_blank"
            rel="noreferrer"
            className="text-xs text-gray-600 hover:text-gray-900 underline"
          >
            Abrir en nueva pestaña ↗
          </a>
        </div>
        <iframe
          src={HEATMAP_URL}
          title="Friction Heatmap"
          className="flex-1 min-h-[720px] w-full bg-white border border-gray-200 rounded-lg shadow-sm"
        />
      </div>
    </AppLayout>
  );
}
