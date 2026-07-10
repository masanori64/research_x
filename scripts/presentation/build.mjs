import { existsSync } from "node:fs";
import { mkdir } from "node:fs/promises";
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const args = new Set(process.argv.slice(2));
const dryRun = args.has("--dry-run");
const slides = path.join(root, "docs", "presentation", "deck.marp");
const facts = path.join(root, "docs", "presentation", "project-facts.json");
const dist = path.join(root, "docs", "presentation", "dist");
const output = path.join(dist, "research-x-presentation.pptx");

function missingContentMessage(filePath) {
  const relative = path.relative(root, filePath).replaceAll(path.sep, "/");
  return `missing required content file: ${relative}; run Stage 2 facts/slides generation first`;
}

async function run(command, commandArgs) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, commandArgs, {
      cwd: root,
      shell: false,
      stdio: "inherit",
    });
    child.on("error", reject);
    child.on("exit", (code) => resolve(code ?? 1));
  });
}

async function main() {
  for (const required of [facts, slides]) {
    if (!existsSync(required)) {
      console.error(missingContentMessage(required));
      return 2;
    }
  }

  const factsCode = await run("uv", [
    "run",
    "python",
    "-m",
    "research_x",
    "presentation",
    "validate-facts",
    "--facts",
    "docs/presentation/project-facts.json",
  ]);
  if (factsCode !== 0) {
    return factsCode;
  }

  if (dryRun) {
    const slidesCode = await run("uv", [
      "run",
      "python",
      "-m",
      "research_x",
      "presentation",
      "validate-slides",
      "--facts",
      "docs/presentation/project-facts.json",
      "--slides",
      "docs/presentation/deck.marp",
      "--allow-missing-assets",
    ]);
    if (slidesCode !== 0) {
      return slidesCode;
    }
    console.log("presentation build dry-run ok");
    return 0;
  }

  await mkdir(dist, { recursive: true });
  const renderCode = await run(process.execPath, ["scripts/presentation/render-d2.mjs"]);
  if (renderCode !== 0) {
    return renderCode;
  }

  const slidesCode = await run("uv", [
    "run",
    "python",
    "-m",
    "research_x",
    "presentation",
    "validate-slides",
    "--facts",
    "docs/presentation/project-facts.json",
    "--slides",
    "docs/presentation/deck.marp",
  ]);
  if (slidesCode !== 0) {
    return slidesCode;
  }

  const marpCli = path.join(root, "node_modules", "@marp-team", "marp-cli", "marp-cli.js");
  return run(process.execPath, [
    marpCli,
    slides,
    "--pptx",
    "--allow-local-files",
    "-o",
    output,
  ]);
}

main()
  .then((code) => process.exit(code))
  .catch((error) => {
    console.error(error instanceof Error ? error.stack || error.message : String(error));
    process.exit(1);
  });
