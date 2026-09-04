import "@testing-library/jest-dom/vitest";

// Polyfill for ResizeObserver (needed by echarts-for-react's auto-resize)
(globalThis as any).ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// jsdom never computes real layout, so clientWidth/clientHeight are always 0
// regardless of CSS. ECharts warns loudly ("Can't get DOM width or height")
// every time it measures a zero-sized container -- give test containers a
// stable, non-zero size so that warning doesn't spam every chart test.
Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, value: 300 });
Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, value: 200 });
