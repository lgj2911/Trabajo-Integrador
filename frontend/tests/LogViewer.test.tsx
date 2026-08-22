import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import { LogViewer } from "../src/components/LogViewer";

type Listener = (event: MessageEvent) => void;

class MockEventSource {
  static instances: MockEventSource[] = [];

  url: string;
  withCredentials: boolean;
  onmessage: Listener | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  private listeners: Record<string, Listener[]> = {};

  constructor(url: string, init?: EventSourceInit) {
    this.url = url;
    this.withCredentials = init?.withCredentials ?? false;
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: Listener) {
    this.listeners[type] = [...(this.listeners[type] ?? []), listener];
  }

  emit(type: "message" | "end", data: unknown) {
    const event = { data: JSON.stringify(data) } as MessageEvent;
    if (type === "message") {
      this.onmessage?.(event);
    } else {
      this.listeners.end?.forEach((listener) => listener(event));
    }
  }

  close() {
    this.closed = true;
  }
}

describe("LogViewer", () => {
  beforeEach(() => {
    MockEventSource.instances = [];
    vi.stubGlobal("EventSource", MockEventSource);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("opens the log stream with credentials for the given session", () => {
    render(<LogViewer sessionId="session-1" />);

    const instance = MockEventSource.instances[0];
    expect(instance).toBeDefined();
    expect(instance.url).toContain("/api/sessions/session-1/logs");
    expect(instance.withCredentials).toBe(true);
  });

  it("renders log lines emitted by the stream", () => {
    render(<LogViewer sessionId="session-1" />);
    const instance = MockEventSource.instances[0];

    act(() => {
      instance.emit("message", { line: "starting scrape", ts: "2026-01-01T00:00:00Z" });
    });

    expect(screen.getByText("starting scrape")).toBeInTheDocument();
  });

  it("shows the final status and closes the stream when it ends", () => {
    render(<LogViewer sessionId="session-1" />);
    const instance = MockEventSource.instances[0];

    act(() => {
      instance.emit("end", { status: "completed" });
    });

    expect(screen.getByText(/final status: completed/i)).toBeInTheDocument();
    expect(instance.closed).toBe(true);
  });
});
