import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, API_TIMEOUT_MS, fetchModules, loginRequest, postSite } from "./api";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function stalled(init?: RequestInit) {
  return new Promise<Response>((_resolve, reject) => {
    const signal = init?.signal;
    if (!signal) return;
    if (signal.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
  });
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("api client", () => {
  it("returns server data for a GET", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ ok: true, data: [{ id: "mod" }] })));
    await expect(fetchModules()).resolves.toEqual([{ id: "mod" }]);
  });

  it("raises ApiError with the server detail and does not retry a 404", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ detail: "Не найдено" }, 404));
    vi.stubGlobal("fetch", fetchMock);
    await expect(fetchModules()).rejects.toMatchObject({ name: "ApiError", status: 404, message: "Не найдено" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("retries an idempotent GET after a network error", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(jsonResponse({ ok: true, data: [{ id: "mod" }] }));
    vi.stubGlobal("fetch", fetchMock);
    const pending = fetchModules();
    await vi.advanceTimersByTimeAsync(1_000);
    await expect(pending).resolves.toEqual([{ id: "mod" }]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("retries a GET that returns 503", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ detail: "busy" }, 503))
      .mockResolvedValueOnce(jsonResponse({ ok: true, data: [] }));
    vi.stubGlobal("fetch", fetchMock);
    const pending = fetchModules();
    await vi.advanceTimersByTimeAsync(1_000);
    await expect(pending).resolves.toEqual([]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("stops a stalled GET at the timeout without a second attempt", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn((_url: string, init?: RequestInit) => stalled(init));
    vi.stubGlobal("fetch", fetchMock);
    const pending = fetchModules();
    const assertion = expect(pending).rejects.toMatchObject({ name: "ApiError", status: 408 });
    await vi.advanceTimersByTimeAsync(API_TIMEOUT_MS);
    await assertion;
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("aborts when the caller signal aborts and does not retry", async () => {
    const fetchMock = vi.fn((_url: string, init?: RequestInit) => stalled(init));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();
    const pending = fetchModules(controller.signal);
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("does not retry a failed POST", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ detail: "no" }, 500));
    vi.stubGlobal("fetch", fetchMock);
    await expect(loginRequest("a@b.c", "secret", true)).rejects.toBeInstanceOf(ApiError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("keeps the Idempotency-Key header on site posts", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true, data: { id: "1" } }));
    vi.stubGlobal("fetch", fetchMock);
    await postSite("projects/1/daily", "a@b.c", { notes: "x" }, "key-1");
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(new Headers(init.headers).get("Idempotency-Key")).toBe("key-1");
  });
});
