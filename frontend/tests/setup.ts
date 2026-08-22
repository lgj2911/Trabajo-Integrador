import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// vitest is configured without `globals: true`, so testing-library's automatic
// cleanup (which relies on detecting a global afterEach) does not register
// itself. Do it explicitly here instead.
afterEach(() => {
  cleanup();
});
