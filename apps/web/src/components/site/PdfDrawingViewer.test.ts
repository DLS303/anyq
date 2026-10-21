import { createElement } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DRAWING_VIEW_TIMEOUT_MS, PdfDrawingViewer } from "./PdfDrawingViewer";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("PdfDrawingViewer", () => {
  it("shows an error and retries when the file cannot be opened", async () => {
    let calls = 0;
    const loadFile = () => {
      calls += 1;
      return Promise.reject(new Error("no"));
    };
    render(createElement(PdfDrawingViewer, { locale: "ru", fileKey: "sheet:A", loadFile }));
    expect((await screen.findByRole("alert")).textContent).toContain("Не удалось открыть чертёж");
    fireEvent.click(screen.getByRole("button", { name: "Повторить" }));
    await waitFor(() => expect(calls).toBeGreaterThanOrEqual(2));
    expect(screen.getByRole("alert").textContent).toContain("Не удалось открыть чертёж");
  });

  it("stops waiting when the file never arrives", async () => {
    vi.useFakeTimers();
    const loadFile = () => new Promise<ArrayBuffer>(() => undefined);
    render(createElement(PdfDrawingViewer, { locale: "kk", fileKey: "sheet:B", loadFile }));
    await vi.advanceTimersByTimeAsync(DRAWING_VIEW_TIMEOUT_MS);
    await vi.runAllTimersAsync();
    expect(screen.getByRole("alert").textContent).toContain("Сызба ашылмады");
    expect(screen.getByRole("button", { name: "Қайталау" })).toBeTruthy();
  });
});
