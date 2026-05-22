import { createBrowserRouter, RouterProvider, Navigate, useParams } from 'react-router-dom';

function CellRedirect() {
  const { sector, function: fn } = useParams();
  return <Navigate to={`/markets/${sector ?? ''}${fn ? `?fn=${fn}` : ''}`} replace />;
}
import { DashboardPage } from '../pages/DashboardPage';
import { CompanyDetailPage } from '../pages/CompanyDetailPage';
import { ValidationPage } from '../pages/ValidationPage';
import { HeatmapPage } from '../pages/HeatmapPage';
import { ConsolePage } from '../pages/ConsolePage';
import { AppShellV2 } from '../components/v2/layout/AppShellV2';
import { MarketsPage } from '../pages/v2/MarketsPage';
import { SectorOverviewPage } from '../pages/v2/SectorOverviewPage';
import { CompanyDetailV2 } from '../pages/v2/CompanyDetailV2';
import { BriefsPage } from '../pages/v2/BriefsPage';
import { VipOpportunitiesPage } from '../pages/v2/VipOpportunitiesPage';
import { VipCompanyDetailPage } from '../pages/v2/VipCompanyDetailPage';
import { PipelineOperationsPage } from '../pages/v2/PipelineOperationsPage';

const router = createBrowserRouter([
  { path: '/', element: <Navigate to="/markets" replace /> },

  {
    element: <AppShellV2 />,
    children: [
      { path: '/markets', element: <MarketsPage /> },
      { path: '/markets/:sector', element: <SectorOverviewPage /> },
      { path: '/markets/:sector/c/:companyId', element: <CompanyDetailV2 /> },
      { path: '/markets/:sector/:function', element: <CellRedirect /> },
      { path: '/opportunities', element: <VipOpportunitiesPage /> },
      { path: '/company/:companyId', element: <VipCompanyDetailPage /> },
      { path: '/briefs', element: <BriefsPage /> },
      { path: '/settings', element: <PipelineOperationsPage /> },
    ],
  },

  { path: '/legacy', element: <Navigate to="/legacy/dashboard" replace /> },
  { path: '/legacy/dashboard', element: <DashboardPage /> },
  { path: '/legacy/console', element: <ConsolePage /> },
  { path: '/legacy/console/:companyId', element: <ConsolePage /> },
  { path: '/legacy/heatmap', element: <HeatmapPage /> },
  { path: '/legacy/companies/:companyId', element: <CompanyDetailPage /> },
  { path: '/legacy/validation', element: <ValidationPage /> },

  { path: '/dashboard', element: <Navigate to="/legacy/dashboard" replace /> },
  { path: '/console', element: <Navigate to="/legacy/console" replace /> },
  { path: '/console/:companyId', element: <Navigate to="/legacy/console" replace /> },
  { path: '/heatmap', element: <Navigate to="/legacy/heatmap" replace /> },
  { path: '/companies/:companyId', element: <Navigate to="/legacy/dashboard" replace /> },
  { path: '/validation', element: <Navigate to="/legacy/validation" replace /> },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}