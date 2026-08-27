/**
 * Build the MiniSearch index for the Episodic subsite.
 *
 * Follows the Netsuke static-index approach, with one Episodic-specific
 * difference: Netsuke hosts its own documentation, so its index covers only
 * on-site pages. Episodic's documentation lives upstream and is linked rather
 * than copied, so this index carries two kinds of record:
 *
 *   - `page` and `section`, extracted from the rendered subsite, linking to
 *     on-site anchors; and
 *   - `document`, read from the committed documentation manifest, linking to
 *     the upstream repository.
 *
 * Searching "idempotency" should therefore surface both the API reference
 * section that explains it and the users' guide that documents it.
 *
 * The index is written into `src/static/`, then copied into the render output
 * by the site's static-assets build step. That makes it a committed generated
 * file, and `--check` fails when it drifts from the content it describes.
 *
 * @file
 * @module scripts/build-episodic-search-index
 */

import { randomUUID } from "node:crypto";
import { mkdir, readdir, readFile, rename, unlink, writeFile } from "node:fs/promises";
import path from "node:path";

import MiniSearch from "minisearch";

const SITE_DIR = "public/episodic";
const MANIFEST_PATH = "templates/episodic/data/docs_manifest.jinja";
const OUTPUT_PATH = "src/static/episodic/assets/search/episodic-search.json";
const SOURCE_BASE = "https://github.com/leynos/episodic/blob/main/";

/**
 * One indexed page, section, or upstream document with its destination.
 *
 * @interface SearchRecord
 * @property {string} id Stable identifier.
 * @property {string} kind One of `page`, `section`, or `document`.
 * @property {string} title Result heading.
 * @property {string} pageTitle Owning page or category.
 * @property {string} sectionTitle Subheading, or the record's classification.
 * @property {string} headings Heading text, for weighting.
 * @property {string} body Searchable text.
 * @property {string} excerpt Shown beneath the result.
 * @property {string} sitePath Destination href.
 */

const INDEX_OPTIONS = {
  fields: ["title", "pageTitle", "sectionTitle", "headings", "body"],
  storeFields: ["title", "sitePath", "pageTitle", "sectionTitle", "excerpt", "kind"],
  searchOptions: {
    boost: { title: 6, pageTitle: 4, sectionTitle: 3, headings: 2 },
    prefix: true,
    fuzzy: 0.15,
  },
};

/**
 * Build or verify the committed search index for the rendered Episodic site.
 *
 * @returns {Promise<void>} Resolves after generating or checking the index.
 */
async function main() {
  const check = process.argv.includes("--check");
  const documents = [...(await collectSitePages()), ...(await collectUpstreamDocuments())];

  if (documents.length === 0) {
    console.error(`No content found. Run \`bun run build:pages\` before building the index.`);
    process.exitCode = 1;
    return;
  }

  const miniSearch = new MiniSearch({
    fields: INDEX_OPTIONS.fields,
    storeFields: INDEX_OPTIONS.storeFields,
  });
  miniSearch.addAll(documents);

  // No build timestamp: the file is committed, and a timestamp would make
  // every rebuild a spurious change and defeat the drift check.
  const payload = `${JSON.stringify(
    { indexOptions: INDEX_OPTIONS, index: JSON.stringify(miniSearch.toJSON()) },
    null,
    2,
  )}\n`;

  const current = await readFile(OUTPUT_PATH, "utf8").catch((error) => {
    if (error?.code === "ENOENT") {
      return "";
    }
    throw error;
  });

  if (check) {
    if (current !== payload) {
      console.error(`${OUTPUT_PATH} is stale. Run \`bun run build:search\` to regenerate it.`);
      process.exitCode = 1;
      return;
    }
    console.log(`${OUTPUT_PATH} matches the rendered site (${documents.length} records).`);
    return;
  }

  /* Skip the write when nothing changed, rather than rewriting identical
     content. The payload is already deliberately free of a build timestamp so
     that a rebuild is not a spurious change; writing it anyway gave that away
     again, because the file lives under `src/`, which `bun run dev` watches.
     Each build rewrote it, the watcher saw a change, and it rebuilt — for as
     long as it was left running. */
  if (current === payload) {
    console.log(`${OUTPUT_PATH} is already current (${documents.length} records indexed)`);
    return;
  }

  await writeIndexAtomically(OUTPUT_PATH, payload);
  console.log(`wrote ${OUTPUT_PATH} (${documents.length} records indexed)`);
}

/**
 * Walk the rendered preview for every published page.
 *
 * @param {string} dir Directory to search.
 * @returns {Promise<string[]>} Paths of every index.html beneath `dir`.
 */
async function findPages(dir) {
  const found = [];
  const entries = await readdir(dir, { withFileTypes: true });
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      found.push(...(await findPages(full)));
    } else if (entry.name === "index.html") {
      found.push(full);
    }
  }
  return found;
}

/**
 * Collect one search document for every rendered Episodic route.
 *
 * @returns {Promise<SearchRecord[]>} Page and section records from the site.
 */
async function collectSitePages() {
  const files = (await findPages(SITE_DIR)).sort();
  const documents = [];
  for (const filePath of files) {
    const html = await readFile(filePath, "utf8");
    documents.push(...extractDocuments(filePath, html));
  }
  return documents;
}

/**
 * Read the documentation manifest without a Jinja runtime.
 *
 * Its ``doc_categories`` payload is a JSON literal committed with the
 * rendered site data.

 * @param {string} manifestPath Manifest to read.
 * @returns {Promise<SearchRecord[]>} One record per upstream document.
 */
async function collectUpstreamDocuments(manifestPath = MANIFEST_PATH) {
  const text = await readFile(manifestPath, "utf8");
  const match = text.match(/\{% set doc_categories = ([\s\S]*?) %\}\n\{% set doc_featured/);
  if (!match) {
    throw new Error(`${manifestPath} does not contain a doc_categories JSON payload.`);
  }
  /** @type {{label: string, type: string, audience: string, blurb: string,
      documents: {title: string, path: string, summary: string}[]}[]} */
  const categories = JSON.parse(match[1]);
  return categories.flatMap((category) =>
    category.documents.map((document) => ({
      id: document.path,
      kind: "document",
      title: document.title,
      pageTitle: category.label,
      sectionTitle: `${category.type} · ${category.audience}`,
      headings: `${category.label} ${category.type} ${category.audience}`,
      body: `${document.title} ${document.summary} ${category.blurb}`,
      excerpt: document.summary,
      sitePath: `${SOURCE_BASE}${document.path}`,
    })),
  );
}

/**
 * @param {string} filePath Rendered page on disk.
 * @param {string} html Its contents.
 * @returns {SearchRecord[]} One page record plus one per section.
 */
function extractDocuments(filePath, html) {
  const sitePath = toSitePath(filePath);
  const mainHtml = matchFirst(html, /<main\b[^>]*>([\s\S]*?)<\/main>/i) ?? html;
  const pageTitle =
    stripTags(matchFirst(mainHtml, /<h1\b[^>]*>([\s\S]*?)<\/h1>/i) ?? "") ||
    stripTags(matchFirst(html, /<title\b[^>]*>([\s\S]*?)<\/title>/i) ?? "") ||
    sitePath;
  const pageExcerpt = firstMeaningfulParagraph(mainHtml);
  const documents = [
    {
      id: sitePath,
      kind: "page",
      title: pageTitle,
      pageTitle,
      sectionTitle: "",
      headings: extractHeadings(mainHtml).join(" "),
      body: normalizeText(mainHtml),
      excerpt: pageExcerpt,
      sitePath,
    },
  ];

  for (const { id: sectionId, html: sectionHtml } of extractSections(mainHtml)) {
    const sectionTitle =
      stripTags(matchFirst(sectionHtml, /<h[2-4]\b[^>]*>([\s\S]*?)<\/h[2-4]>/i) ?? "") || pageTitle;
    const body = normalizeText(sectionHtml);
    if (!body) {
      continue;
    }
    documents.push({
      id: `${sitePath}#${sectionId}`,
      kind: "section",
      title: `${sectionTitle} - ${pageTitle}`,
      pageTitle,
      sectionTitle,
      headings: extractHeadings(sectionHtml).join(" "),
      body,
      excerpt: firstMeaningfulParagraph(sectionHtml) || pageExcerpt,
      sitePath: `${sitePath}#${sectionId}`,
    });
  }

  return documents;
}

/**
 * Extract identified sections while retaining nested section content.
 *
 * @param {string} html Fragment containing section elements.
 * @returns {{id: string, html: string}[]} Identified sections in document order.
 */
function extractSections(html) {
  const stack = [];
  const sections = [];
  for (const match of html.matchAll(/<\/?section\b[^>]*>/gi)) {
    const tag = match[0];
    if (tag.startsWith("</")) {
      const section = stack.pop();
      if (section?.id) {
        sections.push({
          html: html.slice(section.contentStart, match.index),
          id: section.id,
          start: section.start,
        });
      }
      continue;
    }

    const id = /\bid=(?:"([^"]*)"|'([^']*)')/i.exec(tag);
    stack.push({
      contentStart: (match.index ?? 0) + tag.length,
      id: id?.[1] ?? id?.[2] ?? "",
      start: match.index ?? 0,
    });
  }
  return sections
    .sort((left, right) => left.start - right.start)
    .map(({ id, html: content }) => ({
      html: content,
      id,
    }));
}

/**
 * Persist a completed index without exposing a partially written JSON file.
 *
 * @param {string} outputPath Destination of the committed search index.
 * @param {string} payload Complete serialised index.
 * @returns {Promise<void>} Resolves after the replacement is atomic.
 */
async function writeIndexAtomically(outputPath, payload) {
  await mkdir(path.dirname(outputPath), { recursive: true });
  const temporaryPath = `${outputPath}.${randomUUID()}.tmp`;
  try {
    await writeFile(temporaryPath, payload, { flag: "wx" });
    await rename(temporaryPath, outputPath);
  } finally {
    await unlink(temporaryPath).catch(() => undefined);
  }
}

/**
 * @param {string} filePath Rendered page on disk.
 * @returns {string} The site-absolute route it publishes.
 */
function toSitePath(filePath) {
  const relative = path.relative(SITE_DIR, filePath).replace(/\\/g, "/");
  return `/episodic/${relative.replace(/index\.html$/, "")}`;
}

/**
 * @param {string} html Fragment to scan.
 * @returns {string[]} Heading text, outermost first.
 */
function extractHeadings(html) {
  return [...html.matchAll(/<h[1-4]\b[^>]*>([\s\S]*?)<\/h[1-4]>/gi)]
    .map((match) => stripTags(match[1]))
    .filter(Boolean);
}

/**
 * @param {string} html Fragment to scan.
 * @returns {string} The first paragraph long enough to serve as an excerpt.
 */
function firstMeaningfulParagraph(html) {
  for (const match of html.matchAll(/<p\b[^>]*>([\s\S]*?)<\/p>/gi)) {
    const text = stripTags(match[1]);
    if (text.length >= 40) {
      return truncate(text, 180);
    }
  }
  return "";
}

/**
 * @param {string} html Fragment to flatten.
 * @returns {string} Collapsed, truncated plain text.
 */
function normalizeText(html) {
  return truncate(stripTags(html).replace(/\s+/g, " ").trim(), 4000);
}

/**
 * @param {string} html Fragment to flatten.
 * @returns {string} Text with markup and entities resolved.
 */
function stripTags(html) {
  return decodeEntities(
    html
      .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, " ")
      .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, " ")
      .replace(/<[^>]+>/g, " ")
      .replace(/\s+/g, " ")
      .trim(),
  );
}

/**
 * @param {string} text Text carrying HTML entities.
 * @returns {string} Text with the common entities resolved.
 */
function decodeEntities(text) {
  return text
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&copy;/g, "©");
}

/**
 * @param {string} text Text to shorten.
 * @param {number} maxLength Maximum length, including the ellipsis.
 * @returns {string} Text no longer than `maxLength`.
 */
function truncate(text, maxLength) {
  return text.length <= maxLength ? text : `${text.slice(0, maxLength - 1).trimEnd()}…`;
}

/**
 * @param {string} text Text to search.
 * @param {RegExp} pattern Pattern whose first group is returned.
 * @returns {string | null} The first capture, or null.
 */
function matchFirst(text, pattern) {
  return pattern.exec(text)?.[1] ?? null;
}

if (import.meta.main) {
  main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}

export { extractDocuments };
