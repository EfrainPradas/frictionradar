import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom';
import { DashboardPage } from '../pages/DashboardPage';
import { CompanyDetailPage } from '../pages/CompanyDetailPage';
import { ValidationPage } from '../pages/ValidationPage';
import { HeatmapPage } from '../pages/HeatmapPage';

const router = createBrowserRouter([
  { path: '/', element: <Navigate to="/dashboard" replace /> },
  { path: '/dashboard', element: <DashboardPage /> },
  { path: '/heatmap', element: <HeatmapPage /> },
  { path: '/companies/:companyId', element: <CompanyDetailPage /> },
  { path: '/validation', element: <ValidationPage /> },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
