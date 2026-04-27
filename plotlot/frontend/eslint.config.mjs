import { defineConfig, globalIgnores } from "eslint/config";
const loadConfig = async (subpath) => {
  try {
    return (await import(`eslint-config-next/${subpath}`)).default;
  } catch {
    return (await import(`eslint-config-next/${subpath}.js`)).default;
  }
};

const nextVitals = await loadConfig("core-web-vitals");
const nextTs = await loadConfig("typescript");

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
