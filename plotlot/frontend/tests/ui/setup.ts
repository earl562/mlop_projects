import "@testing-library/jest-dom/vitest";

import { afterEach } from "vitest";

const localStorageEntries: Record<string, string> = {};

const testLocalStorage: Storage = {
  get length() {
    return Object.keys(localStorageEntries).length;
  },
  clear() {
    for (const key of Object.keys(localStorageEntries)) {
      delete localStorageEntries[key];
    }
  },
  getItem(key: string) {
    return localStorageEntries[key] ?? null;
  },
  key(index: number) {
    return Object.keys(localStorageEntries)[index] ?? null;
  },
  removeItem(key: string) {
    delete localStorageEntries[key];
  },
  setItem(key: string, value: string) {
    localStorageEntries[key] = value;
  },
};

Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: testLocalStorage,
  writable: true,
});

afterEach(() => {
  testLocalStorage.clear();
});
