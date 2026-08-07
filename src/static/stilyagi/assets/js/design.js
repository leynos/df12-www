// Stilyagi design page: the IR inspector and the capability planner.  Both
// enhance markup that already renders a sensible default state, so the page
// stays readable with scripting disabled.

(() => {
  "use strict";

  const onReady = (fn) => {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn, { once: true });
    } else {
      fn();
    }
  };

  const isActivation = (event) => event.key === "Enter" || event.key === " ";

  /**
   * Collect the linguistic providers an enabled ruleset pulls in.
   *
   * `capabilityLists` is one space-separated capability string per enabled
   * rule.  The core extractor is always present, so it is seeded here rather
   * than declared by any rule.
   */
  function requiredCapabilities(capabilityLists) {
    const capabilities = new Set(["core"]);
    for (const list of capabilityLists) {
      for (const capability of (list || "").split(" ")) {
        if (capability) capabilities.add(capability);
      }
    }
    return capabilities;
  }

  /** Estimated cold start for a capability set; the heaviest provider wins. */
  function coldStartFor(capabilities) {
    if (capabilities.has("grammar")) return "1.4 s";
    if (capabilities.has("spell")) return "260 ms";
    return "40 ms";
  }

  /**
   * Pair the highlighted source spans with the IR tree, and report the active
   * region's label and byte range in the footer.
   */
  function initInspector() {
    const inspector = document.querySelector(".ir-inspector");
    if (!inspector) return;

    const spans = [...inspector.querySelectorAll(".region[data-region]")];
    const nodes = [...inspector.querySelectorAll(".tree-node[data-region]")];
    const label = inspector.querySelector("[data-ir-label]");
    const range = inspector.querySelector("[data-ir-range]");
    if (!nodes.length) return;

    const select = (id) => {
      for (const span of spans) {
        span.classList.toggle("active", span.dataset.region === id);
      }
      let active = null;
      for (const node of nodes) {
        const on = node.dataset.region === id;
        node.classList.toggle("active", on);
        node.setAttribute("aria-pressed", String(on));
        if (on) active = node;
      }
      if (!active) return;
      if (label) label.textContent = active.dataset.label || "";
      if (range) range.textContent = `[${active.dataset.range || ""}]`;
    };

    for (const element of [...spans, ...nodes]) {
      const id = element.dataset.region;
      element.addEventListener("mouseenter", () => select(id));
      element.addEventListener("focus", () => select(id));
      element.addEventListener("click", () => select(id));
      element.addEventListener("keydown", (event) => {
        if (!isActivation(event)) return;
        event.preventDefault();
        select(id);
      });
    }
  }

  /**
   * Recompute which linguistic providers a ruleset pulls in.  The rule rows
   * declare the capabilities they need; everything else is derived.
   */
  function initPlanner() {
    const planner = document.querySelector(".planner");
    if (!planner) return;

    const toggles = [...planner.querySelectorAll(".rule-toggle[data-code]")];
    const providers = [...planner.querySelectorAll(".provider[data-provider]")];
    const ruleCount = planner.querySelector("[data-plan-rules]");
    const providerCount = planner.querySelector("[data-plan-providers]");
    const coldStart = planner.querySelector("[data-plan-coldstart]");
    if (!toggles.length || !providers.length) return;

    const update = () => {
      const active = toggles.filter(
        (toggle) => toggle.getAttribute("aria-checked") === "true",
      );
      const capabilities = requiredCapabilities(
        active.map((toggle) => toggle.dataset.caps),
      );
      const enabled = active.length;

      for (const provider of providers) {
        const loaded = capabilities.has(provider.dataset.provider);
        provider.classList.toggle("loaded", loaded);
        provider.classList.toggle("skipped", !loaded);
        const tag = provider.querySelector("[data-provider-tag]");
        if (tag) tag.textContent = loaded ? "Loaded" : "Skipped";
      }

      if (ruleCount) ruleCount.textContent = String(enabled);
      // The core extractor is not a linguistic provider, so it is not counted.
      if (providerCount) providerCount.textContent = ` ${capabilities.size - 1}`;
      if (coldStart) coldStart.textContent = coldStartFor(capabilities);
    };

    const toggle = (element) => {
      const on = element.getAttribute("aria-checked") === "true";
      element.setAttribute("aria-checked", String(!on));
      element.classList.toggle("on", !on);
      update();
    };

    for (const element of toggles) {
      element.addEventListener("click", () => toggle(element));
      element.addEventListener("keydown", (event) => {
        if (!isActivation(event)) return;
        event.preventDefault();
        toggle(element);
      });
    }
  }

  if (typeof document !== "undefined") {
    onReady(() => {
      initInspector();
      initPlanner();
    });
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      requiredCapabilities: requiredCapabilities,
      coldStartFor: coldStartFor,
    };
  }
})();
