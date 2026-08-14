import { beforeEach, describe, expect, it } from "vitest";
import {
  TaskGoneError,
  clearActiveTask,
  loadActiveTask,
  saveActiveTask,
} from "./task-resume";

describe("active task handles (sessionStorage)", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("round-trips a saved task id", () => {
    expect(loadActiveTask("portfolio")).toBeNull();
    saveActiveTask("portfolio", "task-123");
    expect(loadActiveTask("portfolio")).toBe("task-123");
  });

  it("keeps task kinds isolated", () => {
    saveActiveTask("ips", "task-ips");
    saveActiveTask("portfolio", "task-pf");
    expect(loadActiveTask("ips")).toBe("task-ips");
    expect(loadActiveTask("portfolio")).toBe("task-pf");
    clearActiveTask("ips");
    expect(loadActiveTask("ips")).toBeNull();
    expect(loadActiveTask("portfolio")).toBe("task-pf");
  });

  it("clear removes the handle", () => {
    saveActiveTask("portfolio", "task-123");
    clearActiveTask("portfolio");
    expect(loadActiveTask("portfolio")).toBeNull();
  });

  it("TaskGoneError carries its name for instanceof checks", () => {
    const err = new TaskGoneError();
    expect(err).toBeInstanceOf(Error);
    expect(err.name).toBe("TaskGoneError");
  });
});
