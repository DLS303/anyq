import { createElement } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DEMO_BANNER_TEXT, DEMO_PHONE_STUB_CODE, DEMO_PHONE_STUB_TEXT, SMS_LATER } from "@/lib/signupContact";
import { SignUpWindow } from "./SignUpWindow";

const signupStart = vi.fn();
const signupConfirm = vi.fn();

vi.mock("@/lib/auth", () => ({ useAuth: () => ({ login: vi.fn() }) }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/api", () => ({
  signupStart: (...args: unknown[]) => signupStart(...args),
  signupConfirm: (...args: unknown[]) => signupConfirm(...args),
}));

afterEach(() => {
  cleanup();
  signupStart.mockReset();
  signupConfirm.mockReset();
});

function typeContact(value: string) {
  fireEvent.change(screen.getByLabelText("Телефон или почта"), { target: { value } });
}

describe("sign-up window", () => {
  it("shows the demo banner and confirms a phone with the stub code", async () => {
    signupStart.mockResolvedValue({
      channel: "phone",
      demo_stub: true,
      notice: "Демо: SMS не отправляется. Введите код с экрана",
      access: "none",
      status: "pending",
    });
    signupConfirm.mockResolvedValue({ user: { id: "u-demo" }, token: "t", status: "active" });
    render(createElement(SignUpWindow, { locale: "ru", demo: true }));
    expect(screen.getByText(DEMO_BANNER_TEXT)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Исполнитель услуг" }));
    expect(screen.getAllByText(DEMO_BANNER_TEXT).length).toBeGreaterThan(0);
    typeContact("+77011112233");
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Продолжить" }));
    expect(await screen.findByText(DEMO_PHONE_STUB_TEXT)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /SMS/ })).toBeNull();
    fireEvent.change(screen.getByLabelText("Код подтверждения"), { target: { value: DEMO_PHONE_STUB_CODE } });
    fireEvent.click(screen.getByRole("button", { name: "Подтвердить" }));
    expect(signupConfirm).toHaveBeenCalledWith("+77011112233", DEMO_PHONE_STUB_CODE);
    expect(signupStart).toHaveBeenCalledWith(
      expect.objectContaining({ role: "contractor", contact: "+77011112233", consent_offer_pd: true }),
    );
  });

  it("refuses a non-demo email before calling the server", () => {
    render(createElement(SignUpWindow, { locale: "ru", demo: true }));
    fireEvent.click(screen.getByRole("button", { name: "Заказчик" }));
    typeContact("person@example.com");
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Продолжить" }));
    expect(signupStart).not.toHaveBeenCalled();
    expect(screen.getByText(/@demo\.superapp/)).toBeTruthy();
  });

  it("keeps a phone account on the SMS note without a send button", async () => {
    signupStart.mockResolvedValue({
      channel: "phone",
      notice: SMS_LATER,
      access: "none",
      status: "pending",
    });
    render(createElement(SignUpWindow, { locale: "ru", demo: false }));
    fireEvent.click(screen.getByRole("button", { name: "Поставщик" }));
    typeContact("87011112233");
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Продолжить" }));
    expect(await screen.findByText(SMS_LATER)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Подтвердить" })).toBeNull();
    expect(screen.queryByRole("button", { name: /SMS/ })).toBeNull();
    expect(signupStart).toHaveBeenCalledWith(
      expect.objectContaining({
        role: "supplier",
        contact: "+77011112233",
        account_kind: "individual",
        consent_offer_pd: true,
      }),
    );
  });

  it("sends физ. лицо or юр. лицо as account_kind", async () => {
    signupStart.mockResolvedValue({
      channel: "email",
      notice: "",
      access: "none",
      status: "pending",
    });
    render(createElement(SignUpWindow, { locale: "ru", demo: false }));
    fireEvent.click(screen.getByRole("button", { name: "Заказчик" }));
    const individual = screen.getByRole("radio", { name: "физ. лицо" }) as HTMLInputElement;
    const company = screen.getByRole("radio", { name: "юр. лицо" }) as HTMLInputElement;
    expect(individual.checked).toBe(true);
    fireEvent.click(company);
    typeContact("person@example.com");
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Продолжить" }));
    expect(signupStart).toHaveBeenCalledWith(
      expect.objectContaining({ role: "customer", contact: "person@example.com", account_kind: "company" }),
    );
  });
});
