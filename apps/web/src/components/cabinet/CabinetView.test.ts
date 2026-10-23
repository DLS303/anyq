import { createElement } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CabinetView } from "./CabinetView";

vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: null, token: "", login: vi.fn(), logout: vi.fn() }) }));
vi.mock("@/lib/pilot", () => ({ PILOT_MODE: false, canEditProject: () => false }));
vi.mock("@/lib/registration", () => ({
  REGISTRATION_ENABLED: false,
  publicRegistrationOpen: () => false,
  registerLink: () => null,
}));

afterEach(() => {
  cleanup();
});

describe("cabinet registration link", () => {
  it("hides the company registration link when registration is off", () => {
    render(createElement(CabinetView, { locale: "ru" }));
    expect(screen.queryByRole("link", { name: "Регистрация компании" })).toBeNull();
    expect(screen.getByRole("link", { name: "Войти" }).getAttribute("href")).toBe("/ru/login");
  });
});