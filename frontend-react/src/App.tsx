import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TooltipProvider } from '@/components/ui/tooltip';
import { AppShell } from '@/components/layout/AppShell';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { DashboardPage } from '@/pages/DashboardPage';
import { MapPage } from '@/pages/MapPage';
import { WeeklyPlanPage } from '@/pages/WeeklyPlanPage';
import { NotBuiltPage } from '@/pages/NotBuiltPage';
import { SettingsPage } from '@/pages/SettingsPage';
import { LoginPage } from '@/pages/LoginPage';
import { PendingApprovalPage } from '@/pages/PendingApprovalPage';
import './App.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

/**
 * Route layout:
 *   /login                          — public (Clerk hosted sign-in)
 *   /pending                        — signed-in-but-unapproved holding screen
 *                                     (gates itself; sits outside ProtectedRoute
 *                                     so unapproved users have somewhere to land)
 *   <ProtectedRoute>                — requires signed in + approved=true
 *     <AppShell>                    — top-bar + sidebar layout
 *       /                — Dashboard
 *       /map             — Map View
 *       /plan            — Weekly Plan
 *       /not-built       — Not Built workflow
 *       /settings        — Settings
 *
 * Deep-linking to /settings while signed-out lands on /login, then redirects
 * back after sign-in. Deep-linking while pending lands on /pending.
 */
export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/pending" element={<PendingApprovalPage />} />
            <Route element={<ProtectedRoute />}>
              <Route element={<AppShell />}>
                <Route path="/" element={<DashboardPage />} />
                <Route path="/map" element={<MapPage />} />
                <Route path="/plan" element={<WeeklyPlanPage />} />
                <Route path="/not-built" element={<NotBuiltPage />} />
                <Route path="/settings" element={<SettingsPage />} />
              </Route>
            </Route>
          </Routes>
        </BrowserRouter>
      </TooltipProvider>
    </QueryClientProvider>
  );
}
