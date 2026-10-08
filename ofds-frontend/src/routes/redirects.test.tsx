import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route, type RouteObject } from "react-router-dom";
import { routes } from "./index";
import { ROUTES } from "@/lib/constants";

/**
 * Task 9: old/combined URLs must keep working, redirected into the new
 * product-scoped routes. Rather than mounting the whole app (auth guard +
 * lazy page trees), this renders just the matched route's <Navigate>
 * element in isolation and confirms where it lands.
 */
function findRouteElement(path: string): React.ReactElement {
  const search = (list: RouteObject[]): RouteObject | undefined => {
    for (const r of list) {
      if (r.path === path) return r;
      if (r.children) {
        const found = search(r.children);
        if (found) return found;
      }
    }
    return undefined;
  };
  const match = search(routes);
  if (!match) throw new Error(`No route registered for ${path}`);
  return match.element as React.ReactElement;
}

function renderRedirect(fromPath: string, toPath: string) {
  const element = findRouteElement(fromPath);
  return render(
    <MemoryRouter initialEntries={[fromPath]}>
      <Routes>
        <Route path={fromPath} element={element} />
        <Route path={toPath} element={<div>Landed on {toPath}</div>} />
      </Routes>
    </MemoryRouter>
  );
}

describe("Legacy URL redirects (Task 9)", () => {
  it("/batches -> /funds/batches", () => {
    renderRedirect("/batches", ROUTES.FUNDS_BATCHES);
    expect(screen.getByText(`Landed on ${ROUTES.FUNDS_BATCHES}`)).toBeInTheDocument();
  });

  it("/investors -> /funds/investors", () => {
    renderRedirect("/investors", ROUTES.FUNDS_INVESTORS);
    expect(screen.getByText(`Landed on ${ROUTES.FUNDS_INVESTORS}`)).toBeInTheDocument();
  });

  it("/valuations -> /funds/valuations", () => {
    renderRedirect("/valuations", ROUTES.FUNDS_VALUATIONS);
    expect(screen.getByText(`Landed on ${ROUTES.FUNDS_VALUATIONS}`)).toBeInTheDocument();
  });

  it("/valuations/new -> /funds/valuations/new", () => {
    renderRedirect("/valuations/new", ROUTES.FUNDS_VALUATION_CREATE);
    expect(screen.getByText(`Landed on ${ROUTES.FUNDS_VALUATION_CREATE}`)).toBeInTheDocument();
  });

  it("/shares/deployment -> /shares/batches", () => {
    renderRedirect("/shares/deployment", ROUTES.SHARES_BATCHES);
    expect(screen.getByText(`Landed on ${ROUTES.SHARES_BATCHES}`)).toBeInTheDocument();
  });

  it("/shares/refunds -> /withdrawals", () => {
    renderRedirect("/shares/refunds", ROUTES.WITHDRAWALS);
    expect(screen.getByText(`Landed on ${ROUTES.WITHDRAWALS}`)).toBeInTheDocument();
  });
});

describe("New product-scoped routes are registered (Task 9)", () => {
  it.each([
    "/funds",
    "/funds/:id",
    "/funds/batches",
    "/funds/batches/new",
    "/funds/investors",
    "/funds/valuations",
    "/funds/valuations/new",
    "/shares",
    "/shares/:id",
    "/shares/batches",
    "/shares/batches/new",
    "/shares/investors",
    "/shares/valuations",
    "/shares/valuations/new",
  ])("%s has a registered route", (path) => {
    expect(() => findRouteElement(path)).not.toThrow();
  });
});
