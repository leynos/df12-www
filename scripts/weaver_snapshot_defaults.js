/**
 * @file weaver_snapshot_defaults.js — the user-agent defaults the walker diffs against.
 *
 * Evaluated once per capture on a blank page, before any target page is
 * opened, so that measuring an element's default styles never touches a
 * page being observed. For every HTML element name it creates one bare
 * element, reads its computed style, and reports what differs from an
 * unknown element's — the base every other default is expressed against,
 * and what the walker falls back to for a name not listed here, as
 * `createElement` of that name in a page would have given.
 *
 * Returns a JSON string: `{ base: {prop: value}, deltas: {TAG: {prop: value}} }`.
 * scripts/weaver_snapshot_tools.py substitutes the result into
 * weaver_snapshot_walker.js as `__DEFAULTS__`.
 */
(() => {
  const tags = [
    "a",
    "abbr",
    "address",
    "area",
    "article",
    "aside",
    "audio",
    "b",
    "base",
    "bdi",
    "bdo",
    "blockquote",
    "body",
    "br",
    "button",
    "canvas",
    "caption",
    "cite",
    "code",
    "col",
    "colgroup",
    "data",
    "datalist",
    "dd",
    "del",
    "details",
    "dfn",
    "dialog",
    "div",
    "dl",
    "dt",
    "em",
    "embed",
    "fieldset",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "head",
    "header",
    "hgroup",
    "hr",
    "html",
    "i",
    "iframe",
    "img",
    "input",
    "ins",
    "kbd",
    "label",
    "legend",
    "li",
    "link",
    "main",
    "map",
    "mark",
    "menu",
    "meta",
    "meter",
    "nav",
    "noscript",
    "object",
    "ol",
    "optgroup",
    "option",
    "output",
    "p",
    "picture",
    "pre",
    "progress",
    "q",
    "rp",
    "rt",
    "ruby",
    "s",
    "samp",
    "script",
    "search",
    "section",
    "select",
    "slot",
    "small",
    "source",
    "span",
    "strong",
    "style",
    "sub",
    "summary",
    "sup",
    "table",
    "tbody",
    "td",
    "template",
    "textarea",
    "tfoot",
    "th",
    "thead",
    "time",
    "title",
    "tr",
    "track",
    "u",
    "ul",
    "var",
    "video",
    "wbr",
  ];
  const read = (el) => {
    document.body.appendChild(el);
    const cs = getComputedStyle(el);
    const record = {};
    for (const prop of cs) record[prop] = cs.getPropertyValue(prop);
    el.remove();
    return record;
  };
  const base = read(document.createElement("x-unknown"));
  const deltas = {};
  for (const tag of tags) {
    const record = read(document.createElement(tag.toUpperCase()));
    const delta = {};
    for (const [prop, value] of Object.entries(record)) {
      if (base[prop] !== value) delta[prop] = value;
    }
    for (const prop of Object.keys(base)) {
      if (!(prop in record)) delta[prop] = null;
    }
    if (Object.keys(delta).length) deltas[tag.toUpperCase()] = delta;
  }
  return JSON.stringify({ base, deltas });
})();
