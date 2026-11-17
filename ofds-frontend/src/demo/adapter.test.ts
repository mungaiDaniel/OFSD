import { describe, expect, it, beforeEach } from "vitest";
import { demoAdapter, resetDemoState } from "./adapter";
import { batchService } from "@/services/batchService";
import { authService } from "@/services/authService";
import api from "@/services/api";

// Route the real axios instance through the demo adapter for these tests.
api.defaults.adapter = demoAdapter;

describe("demo adapter", () => {
  beforeEach(resetDemoState);

  it("logs in with any credentials", async () => {
    const res = await authService.login("demo@example.com", "anything");
    expect(res.role).toBe("super_admin");
  });

  it("serves seeded batches with fake investors only", async () => {
    const batches = await batchService.getAll();
    expect(batches.length).toBeGreaterThan(0);
    const detail = await batchService.getById(batches[0]!.id);
    expect(detail.investments!.every((i) => i.investor_email!.endsWith("@example.com"))).toBe(true);
  });

  it("create and delete mutate in-memory state", async () => {
    const before = (await batchService.getAll()).length;
    await batchService.create({ batch_name: "Test batch", share_class_id: 1 });
    expect((await batchService.getAll()).length).toBe(before + 1);
    const created = (await batchService.getAll()).find((b) => b.batch_name === "Test batch")!;
    await batchService.delete(created.id);
    expect((await batchService.getAll()).length).toBe(before);
  });

  it("returns an empty-but-valid payload for unmapped endpoints", async () => {
    const res = await api.get("/some/unmapped/endpoint");
    expect(res.data.status).toBe(200);
  });
});

describe("demo adapter: object-shaped endpoints the Overview page reads", () => {
  it("daily activity has counts", async () => {
    const res = await api.get("/reports/daily-activity?date_from=2026-01-01&date_to=2026-01-31");
    expect(res.data.data.counts.deposits).toBeGreaterThanOrEqual(0);
  });
});
