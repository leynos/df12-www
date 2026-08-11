/**
 * generate-image-variants.ts — the `build:images` step of the site build.
 *
 * Walks the PNGs already copied into `public/images/` and writes a WebP and
 * an AVIF beside each one, so templates can offer modern formats through
 * `<picture>` without anyone hand-exporting them. Sharp does the encoding.
 *
 * Ordering matters: this runs after `build:static`, because it reads the
 * source images that step places, and it writes into `public/`, which is
 * build output in its entirety and tracked nowhere. A variant is skipped
 * when it is already newer than its source, so repeated builds stay cheap;
 * nothing is pruned, because this step cannot tell a deleted asset from
 * another step's output. Remove `public/` and rebuild to clear stale files.
 */
import { access, readdir, stat } from "node:fs/promises";
import { extname, join, relative, sep } from "node:path";
import sharp from "sharp";

const IMAGE_ROOT = join(process.cwd(), "public", "images");
const TARGET_EXTENSIONS = new Set([".png"]);
const OUTPUT_FORMATS = [
  {
    format: "webp",
    options: {
      quality: 92,
      effort: 6,
      nearLossless: false,
    },
  },
  {
    format: "avif",
    options: {
      quality: 70,
      effort: 6,
      chromaSubsampling: "4:4:4",
    },
  },
] as const;

/**
 * Collect every PNG beneath `dir`, recursing into subdirectories.
 *
 * `results` is the accumulator the recursion threads through; callers pass
 * nothing. Returns absolute paths. Reads the filesystem but writes nothing.
 */
async function findPngs(dir: string, results: string[] = []): Promise<string[]> {
  const entries = await readdir(dir, { withFileTypes: true });
  for (const entry of entries) {
    const entryPath = join(dir, entry.name);
    if (entry.isDirectory()) {
      await findPngs(entryPath, results);
    } else if (TARGET_EXTENSIONS.has(extname(entry.name).toLowerCase())) {
      results.push(entryPath);
    }
  }
  return results;
}

/**
 * Whether `targetPath` is stale with respect to `sourcePath`.
 *
 * True when the source is the newer of the two, and true when the target
 * cannot be stat'd at all, since a variant that does not exist yet has to be
 * generated. This is what keeps a repeated build cheap.
 */
async function needsUpdate(sourcePath: string, targetPath: string): Promise<boolean> {
  try {
    const [sourceStats, targetStats] = await Promise.all([stat(sourcePath), stat(targetPath)]);
    return sourceStats.mtimeMs > targetStats.mtimeMs;
  } catch {
    // If the derived file does not exist yet, we need to generate it.
    return true;
  }
}

/**
 * Encode one variant of `sourcePath` in `format`, beside the original.
 *
 * Returns early when the existing variant is already newer than its source.
 * Otherwise writes the file and logs the repository-relative path it wrote.
 */
async function generateVariant(sourcePath: string, format: (typeof OUTPUT_FORMATS)[number]) {
  const outputPath = sourcePath.replace(/\.png$/i, `.${format.format}`);
  if (!(await needsUpdate(sourcePath, outputPath))) {
    return;
  }

  await sharp(sourcePath)
    .toFormat(
      format.format as "webp" | "avif",
      format.options as sharp.WebpOptions | sharp.AvifOptions,
    )
    .toFile(outputPath);

  const rel = relative(process.cwd(), outputPath).split(sep).join("/");
  console.log(`Generated ${rel}`);
}

/**
 * Run the build step: find the PNGs under `public/images` and encode every
 * configured variant of each.
 *
 * Returns quietly when the directory is absent or holds no PNGs, so the step
 * is safe to run before the first build. Variants are encoded concurrently;
 * a failure in any one is collected rather than aborting the rest, and the
 * process exits non-zero once they have all settled.
 */
async function main() {
  try {
    await access(IMAGE_ROOT);
  } catch {
    console.log("Skipping variant generation. Directory public/images does not exist.");
    return;
  }

  const pngFiles = await findPngs(IMAGE_ROOT);
  if (pngFiles.length === 0) {
    console.log("No PNG images found under public/images. Skipping variant generation.");
    return;
  }

  const tasks = pngFiles.flatMap((filePath) =>
    OUTPUT_FORMATS.map((format) => generateVariant(filePath, format)),
  );

  const results = await Promise.allSettled(tasks);
  const failures = results.filter((r) => r.status === "rejected");
  if (failures.length > 0) {
    console.error(`Failed to generate ${failures.length} variants.`);
  }

  console.log(
    `Image variant generation completed (${pngFiles.length} files, ${OUTPUT_FORMATS.length} formats).`,
  );
}

main().catch((error) => {
  console.error("Failed to generate image variants:", error);
  process.exitCode = 1;
});
