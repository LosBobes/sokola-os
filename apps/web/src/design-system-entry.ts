/**
 * Synthesized design-system entry point for /design-sync.
 *
 * apps/web is a private app (no library `dist/` build), so this barrel is
 * the converter's `--entry` in place of a real package entry, it just
 * re-exports the reusable UI primitives so the converter can discover and
 * bundle them.
 */
export * from "./components/ui";
export { BrandMark, ProductShell, PageHeader, ROLE_LABEL } from "./components/shell";
