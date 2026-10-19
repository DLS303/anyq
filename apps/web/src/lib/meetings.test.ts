import { describe, expect, it } from "vitest";
import { menuTabVisible, objectUsesPilotLayout } from "./features";
import {
  MEETING_REQUIRED_FIELDS,
  carryTips,
  openTasksFor,
  pathWins,
  protocolLine,
  taskTransitionAllowed,
  type TaskItem,
} from "./meetings";

const open = (id: string, extra: Partial<TaskItem> = {}): TaskItem => ({
  id,
  meeting_id: "m-1",
  text: "Set the fence",
  assignee_id: "u-1",
  due_date: "2026-10-21",
  status: "open",
  row_version: 1,
  ...extra,
});

describe("meeting tasks", () => {
  it("asks for three fields and keeps the pilot tabs", () => {
    expect(MEETING_REQUIRED_FIELDS).toHaveLength(3);
    expect(objectUsesPilotLayout({ meetings: true }, { demo: false })).toBe(true);
    expect(menuTabVisible("meet", {}, false)).toBe(false);
    expect(menuTabVisible("meet", { meetings: true }, false)).toBe(true);
    expect(menuTabVisible("today", { meetings: true }, false)).toBe(true);
  });

  it("rejects a status move that is not open to done or cancelled", () => {
    expect(taskTransitionAllowed("open", "done")).toBe(true);
    expect(taskTransitionAllowed("open", "cancelled")).toBe(true);
    expect(taskTransitionAllowed("done", "open")).toBe(false);
    expect(taskTransitionAllowed("done", "cancelled")).toBe(false);
    expect(taskTransitionAllowed("cancelled", "done")).toBe(false);
  });

  it("carries only the latest open task", () => {
    const items = [open("a"), open("b", { carried_from_id: "a", meeting_id: "m-2" })];
    expect(carryTips(items).map((item) => item.id)).toEqual(["b"]);
    expect(openTasksFor("u-1", items).map((item) => item.id)).toEqual(["b"]);
    expect(openTasksFor("u-2", items)).toEqual([]);
  });

  it("leaves phones and names out of a protocol line", () => {
    const line = protocolLine("Set the fence", "foreman", "2026-10-21", ["+77019998877"], ["Nuri Owner"]);
    expect(line).toBe("Set the fence · foreman · 2026-10-21");
    expect(line).not.toContain("+77019998877");
    expect(line).not.toContain("Nuri Owner");
  });

  it("ignores a query project id when the path already has one", () => {
    expect(pathWins("project-a", "project-b")).toBe("project-a");
  });
});