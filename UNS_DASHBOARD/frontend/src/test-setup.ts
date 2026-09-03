import "@testing-library/jest-dom/vitest";

// Polyfill for ResizeObserver (needed for recharts in tests)
(globalThis as any).ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};
