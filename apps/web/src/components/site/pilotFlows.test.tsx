import { readFileSync } from "node:fs";
import { createElement } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ObjectBudgetView, ProcOfferCell, ProcSheetLine } from "@/lib/types";

const fixture = JSON.parse(readFileSync("/workspace/apps/api/tests/fixtures/procurement_fake.json", "utf8")) as {
  items: { id: string; name: string; unit: string; qty: number }[];
};
const profilePipe = fixture.items.find((item) => item.id === "it-1");
if (!profilePipe) throw new Error("fixture it-1 is missing");

const quickProcRequest = vi.hoisted(() => vi.fn());
const fetchProcPicker = vi.hoisted(() => vi.fn());
const fetchProcRequests = vi.hoisted(() => vi.fn());
const fetchObjectBudget = vi.hoisted(() => vi.fn());
const repeatPreviousProc = vi.hoisted(() => vi.fn());

const budgetView: ObjectBudgetView = {
  plan: {
    set: true,
    total_kzt: 1_200_000,
    materials_kzt: 975_000,
    works_kzt: 225_000,
    equipment_kzt: 0,
    other_kzt: 0,
  },
  fact_kzt: 930_000,
  fact_by_category: { materials: 930_000, works: 0, equipment: 0, other: 0 },
  procurement_kzt: 930_000,
  manual_kzt: 0,
  remaining_kzt: 270_000,
  used_pct: 77,
  signal: "green",
  elapsed_share: null,
  elapsed_days: null,
  span_days: null,
  schedule_start: "",
  schedule_finish: "",
  forecast_kzt: null,
  forecast_raw_kzt: null,
  forecast_bound_kzt: null,
  forecast_reason: "no_dates",
  overrun_kzt: 0,
  overrun_kind: "none",
  plan_vs_chosen: {
    lines: [
      {
        line_id: "it-6",
        title: "Профнастил С21-0,5 оцинк.",
        unit: "м²",
        qty: 300,
        plan_kzt: 975_000,
        chosen_kzt: 930_000,
        saved_kzt: 45_000,
      },
    ],
    plan_kzt: 975_000,
    chosen_kzt: 930_000,
    total_saved_kzt: 45_000,
  },
  savings: { savings_kzt: 0, base_kzt: 0, savings_pct: 0, requests: 0 },
  company: { name: "ТОО «Демо Стройкомпания»", savings_kzt: 0, base_kzt: 0, savings_pct: 0, requests: 0 },
  expenses: [],
  can_edit: true,
};

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: () => undefined, replace: () => undefined }),
}));

vi.mock("next/link", () => ({
  default: (props: { href: string; children?: unknown }) => createElement("a", { href: props.href }, props.children),
}));

vi.mock("@/lib/auth", () => ({
  useAuth: () => ({
    user: { id: "u-buyer", email: "buyer@example.com", full_name: "Тест Снабженец", role: "owner" },
    token: "token",
    login: () => undefined,
    logout: () => undefined,
  }),
}));

vi.mock("@/lib/api", () => ({
  fetchSiteBundle: async () => ({
    snapshot: {
      project: {
        id: "proj-1",
        title: "Демо-объект: склад 24×48",
        address: "Алматы, тестовый адрес",
        owner_id: "u-buyer",
      },
      health: "green",
      budget_kzt: null,
      committed_kzt: 0,
      actual_kzt: 0,
      open_rfi: 0,
      open_punch: 0,
      open_incidents: 0,
      fail_inspections: 0,
    },
    directory: [],
    daily: [],
    punches: [],
    budget: [],
    changes: [],
    can_approve_changes: false,
    rfis: [],
    inspections: [],
    incidents: [],
    schedule: [],
  }),
  fetchProcRequests,
  fetchProcPicker,
  fetchProjects: async () => [],
  fetchProcSheet: async () => null,
  fetchProcSavings: async () => null,
  quickProcRequest,
  repeatPreviousProc,
  fetchObjectBudget,
  addProjectMember: async () => ({}),
  removeProjectMember: async () => ({}),
  postSite: async () => ({}),
  deleteSite: async () => ({}),
  uploadDailyPhotos: async () => ({}),
  uploadDailyVoice: async () => ({}),
  confirmProcOffer: async () => ({}),
  createProcOffer: async () => ({}),
  createProcRequest: async () => ({ id: "r" }),
  deleteProcOffer: async () => ({}),
  downloadProc: async () => ({}),
  importProcLines: async () => ({ rows: [], created: 0, updated: 0, contact_ignored: false }),
  importProcOffers: async () => ({}),
  openProcFile: () => "",
  patchProcLine: async () => ({}),
  publishProcRequest: async () => ({}),
  repeatProcRequest: async () => ({ request: { id: "d", title: "", status: "collecting" }, lines: [] }),
  selectProcBest: async () => ({}),
  selectProcOffer: async () => ({}),
  setProcDocumentActual: async () => ({}),
  uploadProcDocument: async () => ({}),
  addObjectExpense: async () => ({}),
  deleteObjectExpense: async () => ({}),
  saveObjectBudget: async () => ({}),
}));

import { ObjectBudgetCard } from "./ObjectBudgetCard";
import { PriceCompare } from "./PriceCompare";
import { ProcurementTab } from "./ProcurementTab";
import { ProjectHub } from "./ProjectHub";

function offer(id: string, name: string, price: number, best: boolean): ProcOfferCell {
  return {
    id,
    line_id: "l1",
    supplier_name: name,
    price_kzt: price,
    vat_included: true,
    qty_available: null,
    source_doc_id: null,
    source_label: "fixtures/kp.pdf",
    offer_date: "2026-10-17",
    confirmed: true,
    note: "",
    delivery_term: "",
    is_best: best,
    is_selected: false,
    short: false,
  };
}

afterEach(() => cleanup());

beforeEach(() => {
  quickProcRequest.mockReset();
  quickProcRequest.mockResolvedValue({ request: { id: "req-new" }, line: { id: "line-new" } });
  fetchProcRequests.mockReset();
  fetchProcRequests.mockResolvedValue({
    requests: [],
    access: { member: true, can_request: true, can_offer: true, can_decide: true, can_invoice: true },
    vat_rate: 0.16,
    previous_completed: null,
  });
  fetchProcPicker.mockReset();
  fetchProcPicker.mockImplementation(async (_projectId: string, query = "") => {
    if (query) {
      return {
        recent: [],
        catalog: [{ id: "cat-cable", title: "Кабель ВВГнг 3×2,5", unit: "м" }],
      };
    }
    return {
      recent: [{ title: "Кабель ВВГнг 3×2,5", unit: "м", qty: 40, source: "recent" }],
      catalog: [],
    };
  });
  fetchObjectBudget.mockReset();
  fetchObjectBudget.mockResolvedValue(budgetView);
  repeatPreviousProc.mockReset();
  repeatPreviousProc.mockResolvedValue({
    request: { id: "draft-1", title: "Профнастил С21-0,5 оцинк.", status: "draft" },
    lines: [{ id: "line-1", title: "Профнастил С21-0,5 оцинк.", unit: "м²", qty: 300 }],
  });
});

describe("pilot procurement flows", () => {
  it("sends a new request in three taps from the project hub", async () => {
    render(createElement(ProjectHub, { locale: "ru", id: "proj-1" }));
    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: "Закупки" }).length).toBeGreaterThan(0);
    });
    expect(screen.queryByLabelText("Найти материал")).toBeNull();

    let taps = 0;
    fireEvent.click(screen.getAllByRole("button", { name: "Закупки" })[0]);
    taps += 1;
    const material = await screen.findByRole("button", { name: /Кабель ВВГнг/ });
    fireEvent.click(material);
    taps += 1;
    const send = await screen.findByRole("button", { name: "Отправить" });
    fireEvent.click(send);
    taps += 1;

    await waitFor(() => expect(quickProcRequest).toHaveBeenCalledTimes(1));
    expect(taps).toBeLessThanOrEqual(3);
    expect(quickProcRequest).toHaveBeenCalledWith(
      "proj-1",
      { title: "Кабель ВВГнг 3×2,5", unit: "м", qty: 40 },
      expect.any(String),
    );
    expect(screen.getByLabelText("Найти материал").getAttribute("placeholder")).toBeNull();
  });

  it("keeps the profile pipe unit from the catalog and never falls back to pieces", async () => {
    expect(profilePipe.unit).toBe("м");
    expect(profilePipe.name).toBe("Профтруба 60×40×2");
    fetchProcPicker.mockImplementation(async (_projectId: string, query = "") => {
      const needle = query.toLocaleLowerCase();
      if (needle && profilePipe.name.toLocaleLowerCase().startsWith(needle)) {
        return { recent: [], catalog: [{ id: "it-1", title: profilePipe.name, unit: profilePipe.unit }] };
      }
      return { recent: [], catalog: [] };
    });
    render(createElement(ProcurementTab, { locale: "ru", projectId: "proj-1", projectTitle: "Демо-объект" }));
    const search = await screen.findByLabelText("Найти материал");
    fireEvent.change(search, { target: { value: "Гвоздь" } });
    await waitFor(() => expect(fetchProcPicker).toHaveBeenCalledWith("proj-1", "Гвоздь"));
    expect(screen.queryByRole("button", { name: /Взять/ })).toBeNull();
    expect(screen.queryByText("шт")).toBeNull();
    fireEvent.change(search, { target: { value: "Проф" } });
    const catalog = await waitFor(() => {
      const item = document.querySelector("[data-catalog-item]");
      if (!item) throw new Error("catalog item is not shown yet");
      return item;
    });
    const take = await screen.findByRole("button", { name: /Взять/ });
    expect(catalog.getAttribute("data-unit")).toBe("м");
    expect(take.textContent).toContain(profilePipe.name);
    expect(catalog.compareDocumentPosition(take) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    fireEvent.click(catalog);
    expect(await screen.findByText("м")).toBeTruthy();
    expect(screen.queryByText("шт")).toBeNull();
  });

  it("lists the catalog item above «Взять» and keeps the catalog unit", async () => {
    render(createElement(ProcurementTab, { locale: "ru", projectId: "proj-1", projectTitle: "Демо-объект" }));
    const search = await screen.findByLabelText("Найти материал");
    fireEvent.change(search, { target: { value: "Каб" } });
    const catalog = await waitFor(() => {
      const item = document.querySelector("[data-catalog-item]");
      if (!item) throw new Error("catalog item is not shown yet");
      return item;
    });
    const take = await screen.findByRole("button", { name: /Взять/ });
    expect(catalog.getAttribute("data-unit")).toBe("м");
    expect(catalog.compareDocumentPosition(take) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    fireEvent.click(catalog);
    expect(await screen.findByText("м")).toBeTruthy();
    expect(screen.queryByText("шт")).toBeNull();
  });

  it("shows three suppliers in one row and selects an offer in one tap", () => {
    const onSelect = vi.fn();
    const names = ["ТОО «Тест Металл»", "ТОО «Образец Утепление»", "ИП «Фиктив Строй»"] as const;
    const line: ProcSheetLine = {
      id: "l1",
      pos_no: "1",
      title: "Профнастил С21-0,5 оцинк.",
      unit: "м²",
      qty: 300,
      note: "",
      selected_offer_id: null,
      status: "Сравнили",
      status_code: "compared",
      comparable: true,
      best_offer_id: "pr-10",
      short_qty: false,
      short_available: null,
      short_need: null,
      offers: [],
      cells: {
        [names[0]]: offer("pr-10", names[0], 3100, true),
        [names[1]]: offer("pr-12", names[1], 3250, false),
        [names[2]]: offer("pr-14", names[2], 3400, false),
      },
    };
    render(
      createElement(PriceCompare, {
        locale: "ru",
        lines: [line],
        suppliers: names.map((name, index) => ({ name, total_kzt: 3100 + index * 150, vat_mixed: false })),
        canDecide: true,
        pending: false,
        warnOf: () => undefined,
        onSelect,
      }),
    );
    const cards = document.querySelector("[data-price-cards]");
    const grid = document.querySelector("[data-supplier-grid]");
    expect(cards?.className).toContain("overflow-x-hidden");
    expect(cards?.className.includes("overflow-x-auto")).toBe(false);
    expect(grid?.getAttribute("style")).toContain("repeat(3, minmax(0, 1fr))");
    expect(document.querySelector("[data-best='true']")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Тест Металл/ }));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith("l1", "pr-10");
  });

  it("shows plan minus the chosen price on the money screen", async () => {
    render(createElement(ObjectBudgetCard, { locale: "ru", projectId: "proj-1" }));
    expect(await screen.findByText(/Итого сэкономлено/)).toBeTruthy();
    const saved = document.querySelector("[data-total-saved]");
    expect(saved?.textContent).toContain("45");
    const card = document.querySelector("[data-plan-savings]");
    expect(card?.textContent).toContain("Профнастил");
  });

  it("keeps the expense button above the bottom navigation", async () => {
    render(createElement(ProjectHub, { locale: "ru", id: "proj-1" }));
    await screen.findAllByRole("button", { name: "Деньги" });
    fireEvent.click(screen.getAllByRole("button", { name: "Деньги" })[0]);
    const save = await screen.findByRole("button", { name: "Сохранить расход" });
    const pad = document.querySelector("[data-money-pad]");
    expect(pad?.className).toContain("pb-8");
    expect(pad?.parentElement?.className).toContain("pb-[calc(env(safe-area-inset-bottom)+8rem)]");
    expect(save.className).toContain("scroll-mb-32");
  });
});
