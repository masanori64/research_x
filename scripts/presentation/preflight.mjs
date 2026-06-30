import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { D2 } from "@terrastruct/d2";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

const args = new Set(process.argv.slice(2));
const asJson = args.has("--json");
const requireContent = args.has("--require-content");
const skipD2Sanity = args.has("--skip-d2-sanity");

function rel(...parts) {
  return path.join(root, ...parts);
}

async function packageVersion(packageName) {
  const lock = JSON.parse(await readFile(rel("package-lock.json"), "utf8"));
  return lock.packages[`node_modules/${packageName}`]?.version ?? null;
}

async function d2Sanity() {
  const d2 = new D2();
  const result = await d2.compile("x -> y");
  const svg = await d2.render(result.diagram, result.renderOptions);
  return svg.includes("<svg");
}

async function main() {
  const checks = {
    node: {
      ok: true,
      version: process.version,
    },
    npmPackageSurface: {
      ok: existsSync(rel("package.json")) && existsSync(rel("package-lock.json")),
      packageJson: "package.json",
      lockfile: "package-lock.json",
    },
    marp: {
      ok: existsSync(rel("node_modules", ".bin", process.platform === "win32" ? "marp.cmd" : "marp")),
      package: "@marp-team/marp-cli",
      version: await packageVersion("@marp-team/marp-cli"),
    },
    d2: {
      ok: true,
      package: "@terrastruct/d2",
      version: await packageVersion("@terrastruct/d2"),
      invocation: "node scripts/presentation/render-d2.mjs",
      sanitySvg: skipD2Sanity ? "skipped" : await d2Sanity(),
    },
    directories: {
      ok: existsSync(rel("docs", "presentation", "diagram-systems.md"))
        && existsSync(rel("docs", "presentation", "diagram-design-harness.md")),
      config: existsSync(rel("docs", "presentation", "presentation.config.yaml")),
      diagramSystems: existsSync(rel("docs", "presentation", "diagram-systems.md")),
      diagramDesignHarness: existsSync(rel("docs", "presentation", "diagram-design-harness.md")),
      diagrams: "docs/presentation/diagrams",
      assets: "docs/presentation/assets",
      dist: "docs/presentation/dist",
    },
    content: {
      ok: !requireContent
        || (
          existsSync(rel("docs", "presentation", "project-facts.json"))
          && existsSync(rel("docs", "presentation", "slides.md"))
        ),
      required: requireContent,
      facts: existsSync(rel("docs", "presentation", "project-facts.json")),
      slides: existsSync(rel("docs", "presentation", "slides.md")),
    },
    externalActions: {
      ok: true,
      providerApi: false,
      browser: false,
      plugin: false,
      mcp: false,
      hook: false,
    },
  };

  if (checks.d2.sanitySvg !== "skipped" && checks.d2.sanitySvg !== true) {
    checks.d2.ok = false;
  }

  const blockers = Object.entries(checks)
    .filter(([, value]) => value.ok === false)
    .map(([key]) => key);
  const result = {
    ok: blockers.length === 0,
    stage: "presentation-stage-1-d2-marp-boundary",
    checks,
    blockers,
  };

  if (asJson) {
    console.log(JSON.stringify(result, null, 2));
  } else if (result.ok) {
    console.log("presentation Stage 1 preflight ok");
  } else {
    console.error(`presentation Stage 1 preflight blocked: ${blockers.join(", ")}`);
  }

  return result.ok ? 0 : 2;
}

main()
  .then((code) => process.exit(code))
  .catch((error) => {
    const message = error instanceof Error ? error.stack || error.message : String(error);
    if (asJson) {
      console.log(JSON.stringify({ ok: false, error: message }, null, 2));
    } else {
      console.error(message);
    }
    process.exit(1);
  });
