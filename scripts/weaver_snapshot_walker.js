/* weaver_snapshot_walker.js — the computed-style walker the harness evaluates.
 *
 * A copy of css-view's walker evaluator (src/snapshot/walker.ts, ISC), kept
 * here so the harness can run it inside a page that agent-browser has already
 * settled. css-view drives its own browser and captures the moment the network
 * goes idle, which on Netsuke is before Iconify has fetched its glyphs; the
 * harness needs to say when the page is ready, and agent-browser lets it.
 *
 * Read by scripts/weaver_snapshot_tools.py, which substitutes the four
 * parameters and hands the result to `agent-browser eval`. The output is the
 * same tree css-view writes under `payload.tree`: one node per element, its
 * classes, its bounding box, and the computed properties that differ from
 * the user-agent default for that element — or, for inherited properties,
 * from the parent's value — plus the properties named as always reported,
 * which are written whatever they equal. Margins are always reported: a
 * paragraph's 16px bottom margin is the user-agent default and would
 * otherwise go unrecorded, and the harness folds margins into the gaps
 * between siblings, which needs every margin, default or not.
 */
((inheritedProps, alwaysProps, maxNodes, textClip) => {
  const inherited = new Set(inheritedProps);
  const always = new Set(alwaysProps);

  const iframe = document.createElement("iframe");
  iframe.style.cssText =
    "position:fixed;left:-9999px;top:-9999px;width:0;height:0;border:0;visibility:hidden";
  document.documentElement.appendChild(iframe);

  const defaultsCache = new Map();
  const readDefaults = (tagName) => {
    const upper = tagName.toUpperCase();
    const cached = defaultsCache.get(upper);
    if (cached) return cached;
    const doc = iframe.contentDocument;
    if (!doc || !doc.body) return {};
    const el = doc.createElement(upper);
    doc.body.appendChild(el);
    const cs = iframe.contentWindow?.getComputedStyle(el);
    const record = {};
    if (cs) {
      for (const prop of cs) {
        record[prop] = cs.getPropertyValue(prop);
      }
    }
    el.remove();
    defaultsCache.set(upper, record);
    return record;
  };

  const styleToDict = (cs) => {
    const dict = {};
    for (const property of cs) {
      dict[property] = cs.getPropertyValue(property);
    }
    return dict;
  };

  let visited = 0;

  const trimText = (node) => {
    if (node instanceof HTMLInputElement || node instanceof HTMLTextAreaElement) {
      return node.value ? node.value.slice(0, textClip) : null;
    }
    const text = node.textContent?.trim() ?? "";
    if (!text) return null;
    return text.slice(0, textClip);
  };

  const collect = (node, parentComputed) => {
    visited += 1;
    if (visited > maxNodes) return null;

    const computed = styleToDict(getComputedStyle(node));
    const defaults = readDefaults(node.tagName);
    const diffs = {};

    for (const [property, value] of Object.entries(computed)) {
      if (value == null) continue;
      if (property.startsWith("--")) {
        const baseline = parentComputed?.[property];
        if (baseline === undefined || baseline !== value) {
          diffs[property] = value;
        }
        continue;
      }

      if (always.has(property)) {
        diffs[property] = value;
        continue;
      }

      if (inherited.has(property)) {
        const baseline = parentComputed?.[property] ?? defaults[property];
        if (baseline === undefined || baseline !== value) {
          diffs[property] = value;
        }
      } else {
        const baseline = defaults[property];
        if (baseline === undefined || baseline !== value) {
          diffs[property] = value;
        }
      }
    }

    const rect = node.getBoundingClientRect();
    const snapshot = {
      tag: node.tagName.toLowerCase(),
      id: node.id || null,
      classes: node.className ? String(node.className).trim().split(/\s+/).filter(Boolean) : [],
      role: node.getAttribute("role"),
      name: node.getAttribute("name"),
      text: trimText(node),
      bbox: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
      styleDiff: diffs,
      children: [],
    };

    for (const child of Array.from(node.children)) {
      const childSnapshot = collect(child, computed);
      if (childSnapshot) snapshot.children.push(childSnapshot);
    }

    return snapshot;
  };

  const tree = document.documentElement ? collect(document.documentElement, null) : null;
  iframe.remove();
  return JSON.stringify({ tree, visited });
})(__INHERITED__, __ALWAYS__, __MAX_NODES__, __TEXT_CLIP__);
