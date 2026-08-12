/**
 * Build the MiniSearch full-text index for the Netsuke documentation sub-site.
 *
 * Reads the generated HTML doc pages under public/netsuke/docs/, extracts text
 * and headings, builds a MiniSearch index, and writes the serialised index to
 * public/netsuke/assets/search/docs-search.json.
 *
 * Adapted from netsuke-www/scripts/build-site.mjs.
 *
 * @module
 */

import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

import MiniSearch from "minisearch";

const SITE_DIR = "public/netsuke";
const DOCS_DIR = path.join(SITE_DIR, "docs");
const EXAMPLES_DIR = path.join(SITE_DIR, "examples");
const SEARCH_OUTPUT_DIR = path.join(SITE_DIR, "assets", "search");
const SEARCH_OUTPUT_PATH = path.join(SEARCH_OUTPUT_DIR, "docs-search.json");
const EXAMPLES_SEARCH_OUTPUT_PATH = path.join(SEARCH_OUTPUT_DIR, "examples-search.json");

const INDEX_OPTIONS = {
  fields: ["title", "pageTitle", "sectionTitle", "headings", "body"],
  storeFields: ["title", "sitePath", "pageTitle", "sectionTitle", "excerpt", "kind"],
  searchOptions: {
    boost: {
      title: 6,
      pageTitle: 4,
      sectionTitle: 3,
      headings: 2,
    },
    prefix: true,
    fuzzy: 0.15,
  },
};

/* Build both Netsuke search indices: the documentation set and the examples
   set. The page lists are explicit rather than globbed, so a page joins the
   index only when someone means it to. */
async function main() {
  const docFiles = [
    path.join(DOCS_DIR, "index.html"),
    path.join(DOCS_DIR, "getting-started", "index.html"),
    path.join(DOCS_DIR, "manifest-reference", "index.html"),
    path.join(DOCS_DIR, "rules-and-targets", "index.html"),
    path.join(DOCS_DIR, "templating", "index.html"),
    path.join(DOCS_DIR, "standard-library", "index.html"),
    path.join(DOCS_DIR, "cli", "index.html"),
    path.join(DOCS_DIR, "configuration", "index.html"),
    path.join(DOCS_DIR, "security", "index.html"),
  ];
  const exampleFiles = [
    path.join(EXAMPLES_DIR, "index.html"),
    path.join(EXAMPLES_DIR, "hello-world", "index.html"),
    path.join(EXAMPLES_DIR, "static-site-pipeline", "index.html"),
    path.join(EXAMPLES_DIR, "batch-photo-processing", "index.html"),
    path.join(EXAMPLES_DIR, "visual-design-assets", "index.html"),
    path.join(EXAMPLES_DIR, "basic-c-application", "index.html"),
    path.join(EXAMPLES_DIR, "multi-format-documentation", "index.html"),
  ];

  await buildIndex(docFiles, SEARCH_OUTPUT_PATH);
  await buildIndex(exampleFiles, EXAMPLES_SEARCH_OUTPUT_PATH);
}

/* Read each HTML file, index every document extracted from it with
   MiniSearch, and write the serialized index to `outputPath`, creating its
   directory if need be. Logs how many documents it indexed. */
async function buildIndex(files, outputPath) {
  const documents = [];

  for (const filePath of files) {
    const html = await readFile(filePath, "utf8");
    documents.push(...extractDocuments(filePath, html));
  }

  const miniSearch = new MiniSearch({
    fields: INDEX_OPTIONS.fields,
    storeFields: INDEX_OPTIONS.storeFields,
  });

  miniSearch.addAll(documents);

  await mkdir(path.dirname(outputPath), { recursive: true });
  await writeFile(
    outputPath,
    JSON.stringify(
      {
        generatedAt: new Date().toISOString(),
        indexOptions: INDEX_OPTIONS,
        index: JSON.stringify(miniSearch.toJSON()),
      },
      null,
      2,
    ),
  );

  console.log(`wrote ${outputPath} (${documents.length} documents indexed)`);
}

/* Turn one built page into the documents the index stores: one for the page
   as a whole, then one per `<section>` that carries an id and some text, so a
   search result can land on the section rather than the top of the page.
   Reads only inside `<main>` where present, to keep site chrome out of the
   index. Returns an array; sections with no body text are dropped. */
function extractDocuments(filePath, html) {
  const sitePath = toSitePath(filePath);
  const mainHtml = matchFirst(html, /<main\b[^>]*>([\s\S]*?)<\/main>/i) ?? html;
  const pageTitle =
    stripTags(matchFirst(mainHtml, /<h1\b[^>]*>([\s\S]*?)<\/h1>/i) ?? "") ||
    stripTags(matchFirst(html, /<title\b[^>]*>([\s\S]*?)<\/title>/i) ?? "") ||
    sitePath;
  const pageExcerpt = firstMeaningfulParagraph(mainHtml);
  const headings = extractHeadings(mainHtml);
  const pageBody = normalizeText(mainHtml);
  const docs = [
    {
      id: sitePath,
      kind: "page",
      title: pageTitle,
      pageTitle,
      sectionTitle: "",
      headings: headings.join(" "),
      body: pageBody,
      excerpt: pageExcerpt,
      sitePath,
    },
  ];

  for (const match of mainHtml.matchAll(
    /<section\b[^>]*id="([^"]+)"[^>]*>([\s\S]*?)<\/section>/gi,
  )) {
    const [, sectionId, sectionHtml] = match;
    const sectionTitle =
      stripTags(matchFirst(sectionHtml, /<h[2-4]\b[^>]*>([\s\S]*?)<\/h[2-4]>/i) ?? "") || pageTitle;
    const excerpt = firstMeaningfulParagraph(sectionHtml) || pageExcerpt;
    const body = normalizeText(sectionHtml);

    if (!body) {
      continue;
    }

    docs.push({
      id: `${sitePath}#${sectionId}`,
      kind: "section",
      title: `${sectionTitle} - ${pageTitle}`,
      pageTitle,
      sectionTitle,
      headings: extractHeadings(sectionHtml).join(" "),
      body,
      excerpt,
      sitePath: `${sitePath}#${sectionId}`,
    });
  }

  return docs;
}

/* The URL path a built file is served at: relative to the site root, with
   separators normalized and a trailing `index.html` removed. */
function toSitePath(filePath) {
  const relativePath = path.relative(SITE_DIR, filePath).replace(/\\/g, "/");
  return relativePath.replace(/index\.html$/, "");
}

/* Every h1-h4's text, in document order, with empty ones dropped. These are
   indexed as their own field so a heading match outranks a body match. */
function extractHeadings(html) {
  return [...html.matchAll(/<h[1-4]\b[^>]*>([\s\S]*?)<\/h[1-4]>/gi)]
    .map((match) => stripTags(match[1]))
    .filter(Boolean);
}

/* The first paragraph long enough to serve as a result excerpt — at least 40
   characters, so a one-word lede or a stray caption is skipped — truncated to
   180. Empty string when nothing qualifies. */
function firstMeaningfulParagraph(html) {
  for (const match of html.matchAll(/<p\b[^>]*>([\s\S]*?)<\/p>/gi)) {
    const text = stripTags(match[1]);
    if (text.length >= 40) {
      return truncate(text, 180);
    }
  }

  return "";
}

/* An HTML fragment as indexable plain text: tags stripped, whitespace
   collapsed, and capped at 4000 characters to bound the index size. */
function normalizeText(html) {
  return truncate(stripTags(html).replace(/\s+/g, " ").trim(), 4000);
}

/* Plain text from an HTML fragment. Drops `<script>` and `<style>` contents
   outright rather than merely unwrapping them, so code and CSS never reach
   the index, then removes remaining tags and decodes entities. */
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

/* Decode the handful of named entities the templates actually emit. Not a
   general decoder: anything outside this set passes through unchanged. */
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

/* Cap `text` at `maxLength`, ending with an ellipsis when it had to cut.
   Returns the input untouched when it already fits. */
function truncate(text, maxLength) {
  if (text.length <= maxLength) {
    return text;
  }

  return `${text.slice(0, maxLength - 1).trimEnd()}…`;
}

/* The first capture group of `pattern` in `text`, or null when it does not
   match. */
function matchFirst(text, pattern) {
  const match = pattern.exec(text);
  return match?.[1] ?? null;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
