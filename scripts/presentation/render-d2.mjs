import { existsSync } from "node:fs";
import { mkdir, readdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { D2 } from "@terrastruct/d2";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const args = process.argv.slice(2);

function argValue(name, fallback) {
  const index = args.indexOf(name);
  return index >= 0 && args[index + 1] ? args[index + 1] : fallback;
}

function resolveRepoPath(repoPath) {
  return path.resolve(root, repoPath);
}

async function renderOne(d2, inputPath, outputPath) {
  const source = await readFile(inputPath, "utf8");
  const result = await d2.compile(source);
  const svg = await d2.render(result.diagram, result.renderOptions);
  await mkdir(path.dirname(outputPath), { recursive: true });
  await writeFile(outputPath, svg, "utf8");
  return { input: path.relative(root, inputPath), output: path.relative(root, outputPath) };
}

async function main() {
  const inputArg = argValue("--input", null);
  const outputArg = argValue("--output", null);
  const diagramsDir = resolveRepoPath(argValue("--diagrams-dir", "docs/presentation/diagrams"));
  const assetsDir = resolveRepoPath(argValue("--assets-dir", "docs/presentation/assets"));

  if (inputArg) {
    const inputPath = resolveRepoPath(inputArg);
    const outputPath = resolveRepoPath(
      outputArg || path.join("docs/presentation/assets", `${path.basename(inputArg, ".d2")}.svg`),
    );
    if (!existsSync(inputPath)) {
      console.error(`missing D2 input: ${path.relative(root, inputPath)}`);
      return 2;
    }
    const d2 = new D2();
    const rendered = await renderOne(d2, inputPath, outputPath);
    console.log(JSON.stringify({ ok: true, rendered: [rendered] }, null, 2));
    return 0;
  }

  if (!existsSync(diagramsDir)) {
    console.log(JSON.stringify({ ok: true, rendered: [], message: "no D2 diagrams directory" }, null, 2));
    return 0;
  }

  const files = (await readdir(diagramsDir))
    .filter((file) => file.endsWith(".d2"))
    .sort();
  const d2 = new D2();
  const rendered = [];
  for (const file of files) {
    rendered.push(await renderOne(
      d2,
      path.join(diagramsDir, file),
      path.join(assetsDir, `${path.basename(file, ".d2")}.svg`),
    ));
  }
  console.log(JSON.stringify({ ok: true, rendered }, null, 2));
  return 0;
}

main()
  .then((code) => process.exit(code))
  .catch((error) => {
    console.error(error instanceof Error ? error.stack || error.message : String(error));
    process.exit(1);
  });
