import { access, readdir, stat } from "node:fs/promises";
import { extname, join, dirname, relative, sep } from "node:path";
import sharp from "sharp";

const IMAGE_ROOT = join(process.cwd(), "public", "images");
const TARGET_EXTENSIONS = new Set([".png"]);
const OUTPUT_FORMATS = [
  { format: "webp", options: { quality: 80 } },
  { format: "avif", options: { quality: 45 } },
] as const;

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

async function needsUpdate(sourcePath: string, targetPath: string): Promise<boolean> {
  try {
    const [sourceStats, targetStats] = await Promise.all([stat(sourcePath), stat(targetPath)]);
    return sourceStats.mtimeMs > targetStats.mtimeMs;
  } catch {
    // If the derived file does not exist yet, we need to generate it.
    return true;
  }
}

async function generateVariant(sourcePath: string, format: typeof OUTPUT_FORMATS[number]) {
  const outputPath = sourcePath.replace(/\.png$/i, `.${format.format}`);
  if (!(await needsUpdate(sourcePath, outputPath))) {
    return;
  }

  await sharp(sourcePath)
    .toFormat(format.format as "webp" | "avif", format.options as sharp.WebpOptions | sharp.AvifOptions)
    .toFile(outputPath);

  const rel = relative(process.cwd(), outputPath).split(sep).join("/");
  console.log(`Generated ${rel}`);
}

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

  for (const filePath of pngFiles) {
    for (const format of OUTPUT_FORMATS) {
      await generateVariant(filePath, format);
    }
  }
}

main().catch((error) => {
  console.error("Failed to generate image variants:", error);
  process.exitCode = 1;
});
