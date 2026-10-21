import { createElement } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "@/lib/auth";
import { fetchBootstrap } from "@/lib/api";
import { HomeStage } from "@/components/home/HomeStage";
import { LoginView } from "./LoginView";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => createElement("a", { href }, children),
}));

vi.mock("@/lib/api", () => ({
  fetchBootstrap: vi.fn(),
  loginRequest: vi.fn(),
  registerRequest: vi.fn(),
  fetchMe: vi.fn(),
}));

afterEach(() => cleanup());

function show(flag: boolean) {
  vi.mocked(fetchBootstrap).mockResolvedValue({
    needs_owner: false,
    demo_mode: false,
    registration_enabled: flag,
  });
  return render(
    createElement(AuthProvider, null, createElement(LoginView, { locale: "ru", initialMode: "register" })),
  );
}

describe("registration flag", () => {
  it("starts sign-up from the hero button", () => {
    render(createElement(HomeStage, { locale: "ru" }));
    const cta = screen.getByRole("link", { name: "Зарегистрироваться" });
    expect(cta.getAttribute("href")).toBe("/ru/login?mode=register");
  });

  it("explains empty sign-up fields without placeholders", async () => {
    show(true);
    const signup = await waitFor(() => {
      const form = document.querySelector("[data-signup-form]");
      expect(form).toBeTruthy();
      return form as HTMLFormElement;
    });
    expect(signup.querySelector("[placeholder]")).toBeNull();
    fireEvent.submit(signup);
    expect(await screen.findByText("Укажите компанию")).toBeTruthy();
    expect(screen.getByText("БИН должен быть из 12 цифр")).toBeTruthy();
    expect(screen.getByText("Нужно согласие на обработку персональных данных")).toBeTruthy();
  });

  it("hides sign-up when registration is disabled", async () => {
    show(false);
    await waitFor(() => expect(screen.queryAllByRole("button", { name: "Регистрация" })).toEqual([]));
    expect(screen.getByRole("button", { name: "Войти" })).toBeTruthy();
    expect(screen.queryByText("Компания")).toBeNull();
  });

  it("shows sign-up when registration is enabled", async () => {
    show(true);
    expect((await screen.findAllByRole("button", { name: "Регистрация" })).length).toBeGreaterThan(0);
  });
});
