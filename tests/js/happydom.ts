/**
 * @file Registers happy-dom's window on the global scope before any test runs.
 *
 * Loaded through the `[test].preload` entry in `bunfig.toml`, so every suite
 * under `tests/js` sees a real `document`, `window`, and event machinery
 * without constructing a `Window` by hand. Suites that need an isolated
 * window (the mobile-nav harnesses) still build their own; the two coexist.
 */
import { GlobalRegistrator } from "@happy-dom/global-registrator";

GlobalRegistrator.register();
