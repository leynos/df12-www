/**
 * Mirrors hand-crafted static assets from src/static into public.
 *
 * Everything under public/ is build output. Assets that are authored rather
 * than generated — stylesheets, scripts, images, fonts, favicons — live under
 * src/static and are copied here, preserving their relative paths, so that
 * src/static/mxd/assets/site.css lands at public/mxd/assets/site.css.
 *
 * Copies are skipped when the destination is newer than its source, so
 * repeated builds stay cheap. Stale destinations are not pruned: the pages
 * generator and the image variant step also write into public/, and this
 * script cannot distinguish their output from an asset that has since been
 * deleted. Remove public/ and rebuild for a clean tree.
 */

import { copyFile, mkdir, readdir, stat } from "node:fs/promises";
import { dirname, join, relative, sep } from "node:path";

const SOURCE_ROOT = join(process.cwd(), "src", "static");
const TARGET_ROOT = join(process.cwd(), "public");

async function findFiles(dir: string, results: string[] = []): Promise<string[]> {
  const entries = await readdir(dir, { withFileTypes: true });
  for (const entry of entries) {
    const entryPath = join(dir, entry.name);
    if (entry.isDirectory()) {
      await findFiles(entryPath, results);
    } else if (entry.isFile()) {
      results.push(entryPath);
    }
  }
  return results;
}

async function needsCopy(sourcePath: string, targetPath: string): Promise<boolean> {
  try {
    const [source, target] = await Promise.all([stat(sourcePath), stat(targetPath)]);
    return source.mtimeMs > target.mtimeMs || source.size !== target.size;
  } catch {
    return true;
  }
}

async function main(): Promise<void> {
  try {
    await stat(SOURCE_ROOT);
  } catch {
    console.log("Skipping static copy. Directory src/static does not exist.");
    return;
  }

  const sources = await findFiles(SOURCE_ROOT);
  if (sources.length === 0) {
    console.log("No static assets found under src/static. Skipping static copy.");
    return;
  }

  let copied = 0;
  for (const sourcePath of sources) {
    const targetPath = join(TARGET_ROOT, relative(SOURCE_ROOT, sourcePath));
    if (!(await needsCopy(sourcePath, targetPath))) {
      continue;
    }
    await mkdir(dirname(targetPath), { recursive: true });
    await copyFile(sourcePath, targetPath);
    copied += 1;
    const rel = relative(process.cwd(), targetPath).split(sep).join("/");
    console.log(`copied ${rel}`);
  }

  const skipped = sources.length - copied;
  console.log(`static assets: ${copied} copied, ${skipped} up to date`);
}

await main();
