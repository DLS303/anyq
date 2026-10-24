import { describe, expect, it } from "vitest";
import { t } from "@/i18n/messages";
import { dailyAuthorLabel } from "./report";

describe("dailyAuthorLabel", () => {
  it("shows the employee name to staff and only a role on the public link", () => {
    const entry = { author_name: "Айгуль Тестова", author_role: "foreman" };
    expect(dailyAuthorLabel(entry, t("ru"), "staff")).toBe("Айгуль Тестова");
    expect(dailyAuthorLabel(entry, t("kk"), "staff")).toBe("Айгуль Тестова");
    expect(dailyAuthorLabel(entry, t("ru"), "public")).toBe("Прораб");
    expect(dailyAuthorLabel(entry, t("kk"), "public")).toBe("Шебер");
    expect(dailyAuthorLabel(entry, t("ru"), "public")).not.toContain("Айгуль");
  });
});
