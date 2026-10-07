import { lazy, Suspense } from "react";
import {
  createBrowserRouter,
  Navigate,
  type RouteObject,
} from "react-router-dom";
import { ProtectedRoute } from "./ProtectedRoute";
import { SuperAdminRoute } from "./SuperAdminRoute";
import { AppShell } from "@/components/layout/AppShell";
import LoginPage from "@/pages/auth/LoginPage";
import RegisterPage from "@/pages/auth/RegisterPage";
import { ROUTES } from "@/lib/constants";

// ── Lazy-loaded pages (code splitting for bundle size) ──

const LandingPage = lazy(() => import("@/pages/LandingPage"));
const OverviewPage = lazy(() => import("@/pages/dashboard/OverviewPage"));
const BatchDetailPage = lazy(() => import("@/pages/batches/BatchDetailPage"));
const BatchPerformancePage = lazy(() => import("@/pages/batches/BatchPerformancePage"));
const FundListPage = lazy(() => import("@/pages/funds/FundListPage"));
const FundDetailPage = lazy(() => import("@/pages/funds/FundDetailPage"));
const FundsBatchListPage = lazy(() => import("@/pages/funds/FundsBatchListPage"));
const FundsBatchCreatePage = lazy(() => import("@/pages/funds/FundsBatchCreatePage"));
const FundsInvestorListPage = lazy(() => import("@/pages/funds/FundsInvestorListPage"));
const SharesBatchListPage = lazy(() => import("@/pages/shares/SharesBatchListPage"));
const SharesBatchCreatePage = lazy(() => import("@/pages/shares/SharesBatchCreatePage"));
const SharesInvestorListPage = lazy(() => import("@/pages/shares/SharesInvestorListPage"));
const SharesDeploymentListPage = lazy(() => import("@/pages/shares/SharesDeploymentListPage"));
const SharesRefundsPage = lazy(() => import("@/pages/shares/SharesRefundsPage"));
const ValuationListPage = lazy(() => import("@/pages/valuations/ValuationListPage"));
const ValuationCreatePage = lazy(() => import("@/pages/valuations/ValuationCreatePage"));
const ReportListPage = lazy(() => import("@/pages/reports/ReportListPage"));
const ReportDetailPage = lazy(() => import("@/pages/reports/ReportDetailPage"));
const PortfolioPage = lazy(() => import("@/pages/reports/PortfolioPage"));
const WithdrawalListPage = lazy(() => import("@/pages/withdrawals/WithdrawalListPage"));
const AddInvestorPage = lazy(() => import("../pages/investors/AddInvestorPage"));
const BulkUploadPage = lazy(() => import("../pages/investors/BulkUploadPage"));
const PendingEmailsPage = lazy(() => import("../pages/email/PendingEmailsPage"));
const InvestorOverviewPage = lazy(() => import("../pages/investors/InvestorOverviewPage"));
const InvestorStatementPage = lazy(() => import("../pages/investors/InvestorStatementPage"));
const UserManagementPage = lazy(() => import("@/pages/users/UserManagementPage"));
const AuditLogPage = lazy(() => import("@/pages/audit/AuditLogPage"));
const BackupsPage = lazy(() => import("@/pages/backups/BackupsPage"));
const SettingsPage = lazy(() => import("@/pages/settings/SettingsPage"));

// ── Loading fallback (skeleton) ──

function PageLoader() {
  return (
    <div className="flex items-center justify-center h-64">
      <div
        className="w-6 h-6 border-2 rounded-full animate-spin"
        style={{
          borderColor: "var(--color-border-subtle)",
          borderTopColor: "var(--color-brand-400)",
        }}
      />
    </div>
  );
}

function withSuspense(Component: React.LazyExoticComponent<React.ComponentType<any>>) {
  return (
    <Suspense fallback={<PageLoader />}>
      <Component />
    </Suspense>
  );
}

// ── Route definitions ──

const routes: RouteObject[] = [
  // Public: Landing
  {
    path: "/",
    element: withSuspense(LandingPage),
  },
  {
    path: "/landing",
    element: withSuspense(LandingPage),
  },

  // Public: Auth
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    path: "/auth/login",
    element: <LoginPage />,
  },
  {
    path: "/register",
    element: <RegisterPage />,
  },
  {
    path: "/auth/register",
    element: <RegisterPage />,
  },

  // Protected: Dashboard (all roles)
  {
    element: (
      <ProtectedRoute>
        <AppShell />
      </ProtectedRoute>
    ),
    children: [
      { path: "/overview", element: withSuspense(OverviewPage) },

      // Batches — old combined URLs stay working, redirected into the Funds area
      // (the overwhelmingly common product) so existing bookmarks don't break.
      { path: "/batches", element: <Navigate to={ROUTES.FUNDS_BATCHES} replace /> },
      { path: "/batches/new", element: <Navigate to={ROUTES.FUNDS_BATCH_CREATE} replace /> },
      { path: "/batches/:id", element: withSuspense(BatchDetailPage) },
      { path: "/batches/:id/performance", element: withSuspense(BatchPerformancePage) },

      // Funds area
      { path: "/funds", element: withSuspense(FundListPage) },
      { path: "/funds/:id", element: withSuspense(FundDetailPage) },
      { path: "/funds/batches", element: withSuspense(FundsBatchListPage) },
      { path: "/funds/batches/new", element: withSuspense(FundsBatchCreatePage) },
      { path: "/funds/investors", element: withSuspense(FundsInvestorListPage) },

      // Shares area (DPRP)
      { path: "/shares/batches", element: withSuspense(SharesBatchListPage) },
      { path: "/shares/batches/new", element: withSuspense(SharesBatchCreatePage) },
      { path: "/shares/investors", element: withSuspense(SharesInvestorListPage) },
      { path: "/shares/deployment", element: withSuspense(SharesDeploymentListPage) },
      { path: "/shares/refunds", element: withSuspense(SharesRefundsPage) },

      // Valuations (Funds-only — see Task 3: Shares are valued at price per share, not NAV)
      { path: "/valuations", element: withSuspense(ValuationListPage) },
      { path: "/valuations/new", element: withSuspense(ValuationCreatePage) },

      // Reports
      { path: "/reports", element: withSuspense(ReportListPage) },
      { path: "/reports/portfolio", element: withSuspense(PortfolioPage) },
      { path: "/reports/:id", element: withSuspense(ReportDetailPage) },

      // Withdrawals
      { path: "/withdrawals", element: withSuspense(WithdrawalListPage) },

      // Email
      { path: "/email", element: withSuspense(PendingEmailsPage) },

      // Investor management — old combined directory redirects into Funds, same
      // reasoning as /batches above; add/bulk-upload/detail/statement are shared
      // across both products (see AddInvestorPage's own Product selector).
      { path: "/investors", element: <Navigate to={ROUTES.FUNDS_INVESTORS} replace /> },
      { path: "/investors/add", element: withSuspense(AddInvestorPage) },
      { path: "/investors/bulk-upload", element: withSuspense(BulkUploadPage) },
      { path: "/investors/:clientCode", element: withSuspense(InvestorOverviewPage) },
      { path: "/investors/:clientCode/statement", element: withSuspense(InvestorStatementPage) },

      // Settings
      { path: "/settings", element: withSuspense(SettingsPage) },
    ],
  },

  // Protected: Super Admin only
  {
    element: (
      <SuperAdminRoute>
        <AppShell />
      </SuperAdminRoute>
    ),
    children: [
      { path: "/users", element: withSuspense(UserManagementPage) },
      { path: "/audit-log", element: withSuspense(AuditLogPage) },
      { path: "/backups", element: withSuspense(BackupsPage) },
    ],
  },

  // Dashboard Alias
  { path: "/dashboard", element: <Navigate to="/overview" replace /> },

  // Catch-all 404
  {
    path: "*",
    element: (
      <div
        className="min-h-screen flex items-center justify-center"
        style={{ background: "var(--color-bg-base)" }}
      >
        <div className="text-center">
          <h1 className="text-4xl font-bold mb-2" style={{ color: "var(--color-text-primary)" }}>
            404
          </h1>
          <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>
            Page not found
          </p>
        </div>
      </div>
    ),
  },
];

export const router = createBrowserRouter(routes);
