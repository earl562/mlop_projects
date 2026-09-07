import "@testing-library/jest-dom/vitest";

// jsdom 27 enforces the HTML spec: localStorage is undefined for opaque
// origins (no URL configured). Rather than depend on vitest config internals
// (environmentOptions.jsdom.url — fragile across versions), provide a
// spec-compliant in-memory localStorage polyfill when jsdom doesn't.
// This unblocks any test calling localStorage.clear()/getItem()/setItem().
// (slice 0.3)
if (typeof localStorage === "undefined") {
  const store = new Map<string, string>();
  const localStoragePolyfill: Storage = {
    get length(): number {
      return store.size;
    },
    clear(): void {
      store.clear();
    },
    getItem(key: string): string | null {
      return store.has(key) ? (store.get(key) as string) : null;
    },
    key(index: number): string | null {
      return Array.from(store.keys())[index] ?? null;
    },
    removeItem(key: string): void {
      store.delete(key);
    },
    setItem(key: string, value: string): void {
      store.set(key, String(value));
    },
  };
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    writable: true,
    value: localStoragePolyfill,
  });
}
