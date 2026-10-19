import { createElement, useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { WidgetBoundary } from "./WidgetBoundary";

function Boom({ fail }: { fail: boolean }) {
  if (fail) throw new Error("boom");
  return createElement("p", null, "ready");
}

function Harness() {
  const [fail, setFail] = useState(true);
  return createElement(
    "div",
    null,
    createElement(
      WidgetBoundary,
      {
        message: "Этот блок не загрузился.",
        retryLabel: "Повторить",
      },
      createElement(Boom, { fail }),
    ),
    createElement(
      "button",
      { type: "button", onClick: () => setFail(false) },
      "arm",
    ),
  );
}

describe("WidgetBoundary", () => {
  it("shows a retry action instead of an empty page", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(createElement(Harness));
    expect(screen.getByRole("alert").textContent).toContain("Этот блок не загрузился.");
    fireEvent.click(screen.getByRole("button", { name: "arm" }));
    fireEvent.click(screen.getByRole("button", { name: "Повторить" }));
    expect(screen.getByText("ready")).toBeTruthy();
  });
});
