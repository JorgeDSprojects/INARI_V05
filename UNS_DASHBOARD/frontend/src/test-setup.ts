import "@testing-library/jest-dom/vitest";

// Polyfill for ResizeObserver (needed by echarts-for-react's auto-resize)
(globalThis as any).ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};
