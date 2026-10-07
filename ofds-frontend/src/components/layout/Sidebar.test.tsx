import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { UIProvider } from "@/context/UIContext";
import { AuthProvider } from "@/context/AuthContext";

function renderSidebar(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AuthProvider>
        <UIProvider>
          <Sidebar />
        </UIProvider>
      </AuthProvider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  localStorage.clear();
});

describe("Sidebar — Funds/Shares nav groups", () => {
  it("renders both the Funds and Shares collapsible groups", () => {
    renderSidebar("/overview");
    expect(screen.getByTestId("nav-group-funds")).toBeInTheDocument();
    expect(screen.getByTestId("nav-group-shares")).toBeInTheDocument();
  });

  it("auto-expands the group matching the current route", () => {
    renderSidebar("/shares/batches");

    const sharesGroup = screen.getByTestId("nav-group-shares");
    expect(sharesGroup).toHaveAttribute("aria-expanded", "true");
    // Its items are visible without needing a click.
    expect(screen.getByRole("link", { name: /Deployment & allocation/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Refunds/i })).toBeInTheDocument();
  });

  it("does not auto-expand the other group", () => {
    renderSidebar("/shares/batches");
    const fundsGroup = screen.getByTestId("nav-group-funds");
    expect(fundsGroup).toHaveAttribute("aria-expanded", "false");
  });

  it("lets the user manually expand a group that isn't active", async () => {
    const user = userEvent.setup();
    renderSidebar("/overview"); // neither group active

    const fundsGroup = screen.getByTestId("nav-group-funds");
    expect(fundsGroup).toHaveAttribute("aria-expanded", "false");

    await user.click(fundsGroup);

    expect(fundsGroup).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("link", { name: "Funds & share classes" })).toBeInTheDocument();
  });

  it("lets the user collapse an active group manually", async () => {
    const user = userEvent.setup();
    renderSidebar("/funds/batches");

    const fundsGroup = screen.getByTestId("nav-group-funds");
    expect(fundsGroup).toHaveAttribute("aria-expanded", "true");

    await user.click(fundsGroup);

    expect(fundsGroup).toHaveAttribute("aria-expanded", "false");
  });

  it("each group links to its own product-scoped Batches and Investors routes", () => {
    renderSidebar("/funds/batches");

    const fundsGroup = screen.getByTestId("nav-group-funds");
    expect(fundsGroup).toHaveAttribute("aria-expanded", "true");
    const fundsBatchesLink = screen.getAllByRole("link", { name: "Batches" })[0];
    expect(fundsBatchesLink).toHaveAttribute("href", "/funds/batches");
  });
});
