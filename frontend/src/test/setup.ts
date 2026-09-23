import '@testing-library/jest-dom/vitest';

// jsdom has no ResizeObserver -- ScrollShadowX (used by table-heavy pages
// like DashboardPage/AnalyticsPage) observes its container's size, which
// would otherwise throw "ResizeObserver is not defined" in every test that
// renders a page using it.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = ResizeObserverStub;
