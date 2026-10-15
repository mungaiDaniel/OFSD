import { useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import { ROUTES } from "@/lib/constants";
import { RoleGate } from "./RoleGate";
import { useUI } from "@/context/UIContext";
import {
  LayoutDashboard,
  Layers,
  Landmark,
  Coins,
  TrendingUp,
  FileBarChart,
  ArrowDownUp,
  Users,
  BookUser,
  ShieldCheck,
  Settings,
  PanelLeftClose,
  PanelLeftOpen,
  Mail,
  X,
  DatabaseBackup,
  ChevronDown,
} from "lucide-react";

interface NavItem {
  label: string;
  path: string;
  icon: React.ReactNode;
}

interface NavGroup {
  key: string;
  label: string;
  icon: React.ReactNode;
  items: NavItem[];
}

// ── Shared top-level items (unchanged) ──
const mainNav: NavItem[] = [
  { label: "Overview", path: ROUTES.OVERVIEW, icon: <LayoutDashboard size={17} /> },
  { label: "Reports", path: ROUTES.REPORTS, icon: <FileBarChart size={17} /> },
  { label: "Withdrawals", path: ROUTES.WITHDRAWALS, icon: <ArrowDownUp size={17} /> },
];

// ── Funds / Shares collapsible groups ──
// Task 9: exact item order — Batches, Investors, Valuations, then the
// fund/share-management page itself (named after its product, last).
const navGroups: NavGroup[] = [
  {
    key: "funds",
    label: "Funds",
    icon: <Landmark size={17} />,
    items: [
      { label: "Batches", path: ROUTES.FUNDS_BATCHES, icon: <Layers size={15} /> },
      { label: "Investors", path: ROUTES.FUNDS_INVESTORS, icon: <BookUser size={15} /> },
      { label: "Valuations", path: ROUTES.FUNDS_VALUATIONS, icon: <TrendingUp size={15} /> },
      { label: "Funds", path: ROUTES.FUNDS, icon: <Landmark size={15} /> },
    ],
  },
  {
    key: "shares",
    label: "Shares",
    icon: <Coins size={17} />,
    items: [
      { label: "Batches", path: ROUTES.SHARES_BATCHES, icon: <Layers size={15} /> },
      { label: "Investors", path: ROUTES.SHARES_INVESTORS, icon: <BookUser size={15} /> },
      { label: "Valuations", path: ROUTES.SHARES_VALUATIONS, icon: <TrendingUp size={15} /> },
      { label: "Shares", path: ROUTES.SHARES, icon: <Coins size={15} /> },
    ],
  },
];

const emailNav: NavItem[] = [
  { label: "Email", path: ROUTES.EMAIL, icon: <Mail size={17} /> },
];

const superAdminNav: NavItem[] = [
  { label: "Users", path: ROUTES.USERS, icon: <Users size={17} /> },
  { label: "Audit Log", path: ROUTES.AUDIT_LOG, icon: <ShieldCheck size={17} /> },
  { label: "Backups", path: ROUTES.BACKUPS, icon: <DatabaseBackup size={17} /> },
];

export function Sidebar() {
  const {
    sidebarCollapsed,
    sidebarMobileOpen,
    toggleSidebar,
    setSidebarMobileOpen,
    isMobile,
  } = useUI();
  const location = useLocation();

  /** Desktop: icon rail vs full labels. Mobile drawer always shows labels when open. */
  const showLabels = isMobile || !sidebarCollapsed;
  const desktopWidth = sidebarCollapsed ? "var(--sidebar-collapsed)" : "var(--sidebar-width)";

  const closeMobile = () => setSidebarMobileOpen(false);

  const navLinkProps = (label: string) =>
    isMobile
      ? { onClick: closeMobile }
      : sidebarCollapsed
        ? { title: label }
        : {};

  // A group is "active" when the current route is inside it — drives both the
  // highlighted group header and which groups start expanded.
  const isGroupActive = (group: NavGroup) => group.items.some((item) => location.pathname.startsWith(item.path));

  const [manuallyToggled, setManuallyToggled] = useState<Record<string, boolean>>({});
  const isGroupExpanded = (group: NavGroup) => manuallyToggled[group.key] ?? isGroupActive(group);
  const toggleGroup = (key: string, currentlyExpanded: boolean) =>
    setManuallyToggled((prev) => ({ ...prev, [key]: !currentlyExpanded }));

  return (
    <aside
      className={cn(
        "app-sidebar",
        isMobile && "app-sidebar-mobile",
        !isMobile && sidebarCollapsed && "app-sidebar-desktop-collapsed"
      )}
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        height: "100vh",
        width: isMobile ? "min(100vw, 100%)" : desktopWidth,
        maxWidth: isMobile ? "100vw" : undefined,
        background: "var(--color-bg-surface)",
        borderRight: "1px solid rgba(255,255,255,0.06)",
        display: "flex",
        flexDirection: "column",
        transition: "transform 0.25s ease, width 0.2s ease",
        zIndex: isMobile ? 1050 : 30,
        overflowX: "hidden",
        transform: isMobile && !sidebarMobileOpen ? "translateX(-100%)" : "translateX(0)",
        boxShadow: isMobile && sidebarMobileOpen ? "8px 0 32px rgba(0,0,0,0.35)" : undefined,
      }}
      aria-hidden={isMobile ? !sidebarMobileOpen : undefined}
    >
      {/* Logo + mobile close */}
      <div
        style={{
          height: "var(--topbar-height)",
          display: "flex",
          alignItems: "center",
          padding: isMobile ? "0 0.75rem 0 1rem" : sidebarCollapsed ? "0 1rem" : "0 1.25rem",
          borderBottom: "1px solid rgba(255,255,255,0.06)",
          flexShrink: 0,
          justifyContent: "space-between",
          gap: "0.5rem",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: isMobile || !sidebarCollapsed ? "flex-start" : "center",
            flex: 1,
            minWidth: 0,
            overflow: "hidden",
          }}
        >
          <div style={{ position: "relative", height: "36px", width: "auto", display: "flex", alignItems: "center" }}>
            <img
              alt="AXYS Investment Bank"
              src="/axys-logo.webp"
              style={{
                height: "34px",
                width: "auto",
                maxWidth: "180px",
                objectFit: "contain",
                opacity: isMobile || !sidebarCollapsed ? 1 : 0,
                transition: "opacity 0.25s",
                pointerEvents: isMobile || !sidebarCollapsed ? "auto" : "none",
                position: "absolute",
                left: 0,
              }}
            />
            <img
              alt="AXYS Investment Bank"
              src="/axys-emblem.webp"
              style={{
                height: "34px",
                width: "34px",
                objectFit: "contain",
                opacity: isMobile || !sidebarCollapsed ? 0 : 1,
                transition: "opacity 0.25s",
                pointerEvents: isMobile || !sidebarCollapsed ? "none" : "auto",
                position: "relative",
                left: 0,
              }}
            />
          </div>
        </div>
        {isMobile && (
          <button
            type="button"
            className="btn p-2 border-0 rounded-2"
            onClick={closeMobile}
            style={{ color: "var(--color-text-secondary)", background: "rgba(255,255,255,0.06)" }}
            aria-label="Close menu"
          >
            <X size={20} />
          </button>
        )}
      </div>

      {/* Main nav */}
      <nav className="sidebar-nav flex-grow-1 py-2 px-2" style={{ overflowY: "auto" }}>
        <ul className="nav flex-column mb-0">
          {mainNav.map((item) => (
            <li className="nav-item" key={item.path}>
              <NavLink
                to={item.path}
                className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
                {...navLinkProps(item.label)}
              >
                <span style={{ flexShrink: 0 }}>{item.icon}</span>
                {showLabels && <span className="text-truncate">{item.label}</span>}
              </NavLink>
            </li>
          ))}
        </ul>

        <hr style={{ borderColor: "rgba(255,255,255,0.07)", margin: "0.75rem 0.5rem" }} />

        {/* Funds / Shares collapsible groups */}
        <ul className="nav flex-column mb-0" role="tree">
          {navGroups.map((group) => {
            const active = isGroupActive(group);
            const expanded = isGroupExpanded(group);
            return (
              <li className="nav-item" key={group.key}>
                <button
                  type="button"
                  onClick={() => (sidebarCollapsed && !isMobile ? toggleSidebar() : toggleGroup(group.key, expanded))}
                  aria-expanded={expanded}
                  data-testid={`nav-group-${group.key}`}
                  className="nav-link w-100 d-flex align-items-center"
                  style={{
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    color: active ? "var(--color-text-primary)" : "var(--color-text-secondary)",
                    fontWeight: active ? 600 : 500,
                    justifyContent: sidebarCollapsed && !isMobile ? "center" : "flex-start",
                  }}
                  title={group.label}
                >
                  <span style={{ flexShrink: 0 }}>{group.icon}</span>
                  {showLabels && (
                    <>
                      <span className="text-truncate flex-grow-1 text-start">{group.label}</span>
                      <ChevronDown
                        size={14}
                        style={{
                          flexShrink: 0,
                          transition: "transform 0.15s",
                          transform: expanded ? "rotate(0deg)" : "rotate(-90deg)",
                          opacity: 0.6,
                        }}
                      />
                    </>
                  )}
                </button>

                {showLabels && expanded && (
                  <ul className="nav flex-column mb-0" role="group" style={{ paddingLeft: "22px" }}>
                    {group.items.map((item) => (
                      <li className="nav-item" key={item.path}>
                        <NavLink
                          to={item.path}
                          className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
                          style={{ fontSize: "13px" }}
                          {...navLinkProps(item.label)}
                        >
                          <span style={{ flexShrink: 0 }}>{item.icon}</span>
                          <span className="text-truncate">{item.label}</span>
                        </NavLink>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>

        <hr style={{ borderColor: "rgba(255,255,255,0.07)", margin: "0.75rem 0.5rem" }} />

        <ul className="nav flex-column mb-0">
          {emailNav.map((item) => (
            <li className="nav-item" key={item.path}>
              <NavLink
                to={item.path}
                className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
                {...navLinkProps(item.label)}
              >
                <span style={{ flexShrink: 0 }}>{item.icon}</span>
                {showLabels && <span className="text-truncate">{item.label}</span>}
              </NavLink>
            </li>
          ))}
        </ul>

        <hr style={{ borderColor: "rgba(255,255,255,0.07)", margin: "0.75rem 0.5rem" }} />

        <RoleGate allowedRoles={["super_admin"]}>
          {showLabels && (
            <p
              className="mb-2 px-3"
              style={{
                color: "var(--color-text-tertiary)",
                fontSize: "10px",
                fontWeight: 700,
                textTransform: "uppercase",
                letterSpacing: "0.1em",
              }}
            >
              Super Admin
            </p>
          )}
          <ul className="nav flex-column mb-0">
            {superAdminNav.map((item) => (
              <li className="nav-item" key={item.path}>
                <NavLink
                  to={item.path}
                  className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
                  {...navLinkProps(item.label)}
                >
                  <span style={{ flexShrink: 0 }}>{item.icon}</span>
                  {showLabels && <span className="text-truncate">{item.label}</span>}
                </NavLink>
              </li>
            ))}
          </ul>
        </RoleGate>
      </nav>

      {/* Bottom: Settings + desktop collapse / mobile hint */}
      <div
        className="sidebar-nav py-2 px-2"
        style={{ borderTop: "1px solid rgba(255,255,255,0.06)", flexShrink: 0 }}
      >
        <ul className="nav flex-column mb-0">
          <li className="nav-item">
            <NavLink
              to={ROUTES.SETTINGS}
              className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
              {...navLinkProps("Settings")}
            >
              <Settings size={17} />
              {showLabels && <span>Settings</span>}
            </NavLink>
          </li>
        </ul>

        {!isMobile && (
          <button
            type="button"
            onClick={toggleSidebar}
            className="nav-link w-100 mt-1 d-flex align-items-center"
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              justifyContent: sidebarCollapsed ? "center" : "flex-start",
              gap: "0.5rem",
            }}
            title={sidebarCollapsed ? "Expand sidebar" : "Collapse to icons"}
          >
            {sidebarCollapsed ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}
            {showLabels && <span>{sidebarCollapsed ? "Expand" : "Collapse"}</span>}
          </button>
        )}
      </div>
    </aside>
  );
}
