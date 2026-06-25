import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const outDir = path.join(root, "docs", "uml");
const width = 1600;
const height = 1000;
const palette = {
  ink: "#1f2933",
  blue: "#244766",
  line: "#0d32b2",
  red: "#dc2626",
  bg: "#ffffff",
  fill: "#f7f8fe",
  muted: "#eef3f7",
  note: "#fff7d6",
};

function esc(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function textLines(lines, x, y, opts = {}) {
  const size = opts.size ?? 24;
  const weight = opts.weight ?? 500;
  const color = opts.color ?? palette.ink;
  const anchor = opts.anchor ?? "middle";
  const gap = opts.gap ?? Math.round(size * 1.25);
  const tspans = lines.map((line, index) => (
    `<tspan x="${x}" dy="${index === 0 ? 0 : gap}">${esc(line)}</tspan>`
  )).join("");
  return `<text x="${x}" y="${y}" font-size="${size}" font-weight="${weight}" text-anchor="${anchor}" fill="${color}">${tspans}</text>`;
}

function title(label) {
  return textLines([label], 72, 90, { size: 44, weight: 700, color: palette.blue, anchor: "start" });
}

function rect(x, y, w, h, lines, opts = {}) {
  const fill = opts.fill ?? palette.fill;
  const stroke = opts.stroke ?? palette.line;
  const body = textLines(lines, x + w / 2, y + h / 2 - ((lines.length - 1) * 11), {
    size: opts.size ?? 21,
    weight: opts.weight ?? 700,
    gap: opts.gap ?? 26,
  });
  return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${opts.rx ?? 0}" fill="${fill}" stroke="${stroke}" stroke-width="2"/>${body}`;
}

function packageBox(x, y, w, h, name, bodyLines = []) {
  return [
    `<path d="M${x} ${y + 32} L${x} ${y + h} L${x + w} ${y + h} L${x + w} ${y + 32} L${x + 170} ${y + 32} L${x + 145} ${y} L${x} ${y} Z" fill="${palette.fill}" stroke="${palette.line}" stroke-width="2"/>`,
    textLines([name], x + 18, y + 23, { size: 20, weight: 700, anchor: "start" }),
    ...bodyLines.map((line, index) => textLines([line], x + 24, y + 80 + index * 34, { size: 20, weight: 500, anchor: "start" })),
  ].join("");
}

function ellipse(x, y, w, h, lines) {
  return `<ellipse cx="${x + w / 2}" cy="${y + h / 2}" rx="${w / 2}" ry="${h / 2}" fill="${palette.fill}" stroke="${palette.line}" stroke-width="2"/>${textLines(lines, x + w / 2, y + h / 2 - ((lines.length - 1) * 11), { size: 21, weight: 700, gap: 26 })}`;
}

function actor(x, y, label) {
  return [
    `<circle cx="${x}" cy="${y}" r="24" fill="${palette.bg}" stroke="${palette.line}" stroke-width="2"/>`,
    `<line x1="${x}" y1="${y + 24}" x2="${x}" y2="${y + 96}" stroke="${palette.line}" stroke-width="2"/>`,
    `<line x1="${x - 46}" y1="${y + 48}" x2="${x + 46}" y2="${y + 48}" stroke="${palette.line}" stroke-width="2"/>`,
    `<line x1="${x}" y1="${y + 96}" x2="${x - 44}" y2="${y + 154}" stroke="${palette.line}" stroke-width="2"/>`,
    `<line x1="${x}" y1="${y + 96}" x2="${x + 44}" y2="${y + 154}" stroke="${palette.line}" stroke-width="2"/>`,
    textLines(label.split("\n"), x, y + 198, { size: 21, weight: 700 }),
  ].join("");
}

function arrow(x1, y1, x2, y2, label = "", opts = {}) {
  const stroke = opts.stroke ?? palette.line;
  const dash = opts.dash ? ' stroke-dasharray="10 8"' : "";
  const marker = opts.open ? "url(#openArrow)" : "url(#arrow)";
  const line = `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${stroke}" stroke-width="2.4"${dash} marker-end="${marker}"/>`;
  if (!label) return line;
  return `${line}${textLines([label], (x1 + x2) / 2, (y1 + y2) / 2 - 10, { size: 18, weight: 600, color: stroke })}`;
}

function curvedArrow(pathD, label = "", x = 0, y = 0, opts = {}) {
  const stroke = opts.stroke ?? palette.line;
  const dash = opts.dash ? ' stroke-dasharray="10 8"' : "";
  return [
    `<path d="${pathD}" fill="none" stroke="${stroke}" stroke-width="2.4"${dash} marker-end="url(#arrow)"/>`,
    label ? textLines([label], x, y, { size: 18, weight: 600, color: stroke }) : "",
  ].join("");
}

function note(x, y, w, h, lines) {
  return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="0" fill="${palette.note}" stroke="#b08900" stroke-width="2"/>${textLines(lines, x + 18, y + 35, { size: 19, weight: 600, anchor: "start", gap: 26 })}`;
}

function state(x, y, w, h, lines, opts = {}) {
  return rect(x, y, w, h, lines, { rx: 20, fill: opts.fill ?? palette.fill, stroke: opts.stroke ?? palette.line, size: opts.size ?? 20 });
}

function sequenceParticipant(x, name) {
  return [
    rect(x - 95, 145, 190, 58, name.split("\n"), { size: 18 }),
    `<line x1="${x}" y1="203" x2="${x}" y2="860" stroke="#8ca0b3" stroke-width="2" stroke-dasharray="8 8"/>`,
  ].join("");
}

function activation(x, y, h) {
  return `<rect x="${x - 9}" y="${y}" width="18" height="${h}" fill="#dce8f4" stroke="${palette.line}" stroke-width="1.5"/>`;
}

function frame(diagramName, body) {
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
<defs>
  <marker id="arrow" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto"><path d="M0,0 L12,6 L0,12 Z" fill="${palette.line}"/></marker>
  <marker id="openArrow" markerWidth="14" markerHeight="14" refX="12" refY="7" orient="auto"><path d="M1,1 L13,7 L1,13" fill="none" stroke="${palette.line}" stroke-width="2"/></marker>
  <style>
    text { font-family: "Yu Gothic", "Meiryo", "Aptos", "Segoe UI", sans-serif; }
  </style>
</defs>
<rect width="100%" height="100%" fill="${palette.bg}"/>
${title(diagramName)}
${body}
</svg>`;
}

const diagrams = [
  {
    file: "01-use-case",
    title: "UML Use Case: research_x利用者視点",
    reason: "採用: SI事業者が利用者・AI agent・承認者の責務を把握するため。",
    svg: () => frame("UML Use Case: research_x利用者視点", [
      actor(145, 250, "開発者\nSI事業者"),
      actor(145, 610, "AI\nエージェント"),
      actor(1450, 430, "承認者\nOwner"),
      `<rect x="310" y="170" width="900" height="660" rx="8" fill="#fbfcfe" stroke="#7b8da0" stroke-width="2"/>`,
      textLines(["research_x Memory/Search System"], 760, 215, { size: 26, weight: 700, color: palette.blue }),
      ellipse(380, 260, 260, 90, ["Xデータを取得"]),
      ellipse(710, 260, 300, 90, ["共有Storeへ正規化"]),
      ellipse(420, 410, 300, 90, ["memory corpusを構築"]),
      ellipse(760, 410, 300, 90, ["ローカル検索"]),
      ellipse(420, 560, 300, 90, ["source bundle復元"]),
      ellipse(760, 560, 300, 90, ["citation-ready context"]),
      ellipse(585, 700, 330, 90, ["回答workflow実行"]),
      ellipse(1030, 700, 250, 90, ["Provider/API承認"]),
      arrow(220, 330, 380, 305),
      arrow(220, 690, 420, 455),
      arrow(220, 690, 760, 455),
      arrow(220, 690, 585, 745),
      arrow(1325, 520, 1155, 745, "承認", { stroke: palette.red }),
      arrow(640, 305, 710, 305),
      arrow(720, 455, 760, 455),
      arrow(570, 650, 625, 700),
      arrow(910, 650, 850, 700),
    ].join("")),
  },
  {
    file: "02-component",
    title: "UML Component: 主要実装部品",
    reason: "採用: 実装分担・レビュー境界をC4より一段詳しく示すため。",
    svg: () => frame("UML Component: 主要実装部品", [
      rect(80, 180, 230, 95, ["<<component>>", "research_x CLI"]),
      rect(410, 160, 260, 95, ["<<component>>", "SessionBroker"]),
      rect(410, 310, 260, 95, ["<<component>>", "Acquisition Pipeline"]),
      rect(760, 250, 260, 95, ["<<component>>", "Adapter Catalog"]),
      rect(1110, 250, 260, 95, ["<<component>>", "External X Providers"], { stroke: palette.red }),
      rect(410, 510, 260, 95, ["<<component>>", "Shared X Store"]),
      rect(760, 510, 260, 95, ["<<component>>", "Memory Schema"]),
      rect(1110, 510, 260, 95, ["<<component>>", "Search / Context"]),
      rect(760, 700, 260, 95, ["<<component>>", "Workflow / Answer"]),
      rect(1110, 700, 260, 95, ["<<component>>", "API Budget Guard"], { stroke: palette.red }),
      arrow(310, 225, 410, 205),
      arrow(310, 225, 410, 355),
      arrow(670, 355, 760, 295),
      arrow(1020, 295, 1110, 295, "gated", { stroke: palette.red, dash: true }),
      arrow(540, 405, 540, 510),
      arrow(670, 555, 760, 555),
      arrow(1020, 555, 1110, 555),
      arrow(890, 605, 890, 700),
      arrow(1240, 700, 1020, 760, "blocks real calls", { stroke: palette.red, dash: true }),
      note(80, 735, 430, 110, ["Provider/APIは実装部品として存在するが、", "no-quota freeze中は承認なしに実行しない。"]),
    ].join("")),
  },
  {
    file: "03-package",
    title: "UML Package: コード配置と依存",
    reason: "採用: SI事業者が最初に読むpackage境界を示すため。",
    svg: () => frame("UML Package: コード配置と依存", [
      packageBox(90, 180, 280, 180, "research_x.cli", ["command parser", "gates / options"]),
      packageBox(470, 150, 340, 190, "research_x.pipeline", ["provider chain", "evidence write", "merge / dedupe"]),
      packageBox(920, 150, 340, 190, "research_x.adapters", ["catalog", "provider implementations"]),
      packageBox(470, 430, 340, 190, "research_x.x_store", ["tweets", "bookmarks", "media / edges"]),
      packageBox(920, 430, 390, 250, "research_x.memory", ["schema / corpus / search", "context / citation", "workflow / answer", "api_budget / eval"]),
      packageBox(90, 520, 280, 160, "research_x.presentation", ["facts validator", "slides validator"]),
      packageBox(90, 730, 300, 190, "tests", ["presentation", "memory", "boundary checks"]),
      arrow(370, 235, 470, 235),
      arrow(810, 245, 920, 245),
      arrow(640, 340, 640, 430),
      arrow(810, 525, 920, 525),
      arrow(240, 730, 240, 680),
      arrow(390, 835, 470, 610),
      arrow(390, 860, 920, 610),
    ].join("")),
  },
  {
    file: "04-deployment",
    title: "UML Deployment: 実行配置",
    reason: "採用: ローカル実行・秘密情報・外部Providerゲートを明確化するため。",
    svg: () => frame("UML Deployment: 実行配置", [
      rect(90, 180, 460, 540, ["<<node>>", "Developer Workstation"], { size: 24, fill: "#fbfcfe" }),
      rect(150, 285, 340, 85, ["Python / uv", "research_x CLI"]),
      rect(150, 410, 340, 85, ["SQLite", "runs/x_data.sqlite3"]),
      rect(150, 535, 340, 85, ["Local filesystem", ".secrets / runs / docs"]),
      rect(690, 210, 350, 160, ["<<execution environment>>", "Node tooling", "D2 / Marp / UML asset build"]),
      rect(690, 510, 350, 160, ["<<database>>", "Memory tables", "FTS / workflow / citations"]),
      rect(1160, 310, 320, 160, ["<<external node>>", "X / Provider APIs", "承認ゲート"], { stroke: palette.red }),
      rect(1160, 600, 320, 120, ["<<artifact>>", "SVG / PNG", "review assets"]),
      arrow(490, 330, 690, 290),
      arrow(490, 455, 690, 590),
      arrow(550, 330, 1160, 390, "blocked by default", { stroke: palette.red, dash: true }),
      arrow(1040, 290, 1160, 650),
      note(760, 760, 620, 110, ["秘密情報とprovider呼び出しは同じ図に置くが、", "実行権限は図ではなくAGENTS/予算ゲートが決める。"]),
    ].join("")),
  },
  {
    file: "05-class-core",
    title: "UML Class: 中核データ構造",
    reason: "採用: 実装レビューで型・永続化・workflow traceの対応を確認するため。",
    svg: () => frame("UML Class: 中核データ構造", [
      rect(80, 170, 300, 140, ["AcquisitionTarget", "+ kind", "+ value", "+ limit"], { size: 20 }),
      rect(470, 170, 300, 160, ["FetchOutcome", "+ adapter_id", "+ status", "+ items", "+ error"], { size: 20 }),
      rect(860, 170, 300, 160, ["ProviderAttempt", "+ provider_id", "+ failure_kind", "+ evidence_path"], { size: 20 }),
      rect(1240, 170, 300, 160, ["PipelineTargetResult", "+ status", "+ items", "+ attempts"], { size: 20 }),
      rect(80, 455, 300, 160, ["MemorySearchResult", "+ doc_id", "+ score", "+ evidence_status"], { size: 20 }),
      rect(470, 455, 300, 160, ["ContextBundle", "+ retrieved_hits", "+ context_chunks", "+ citations"], { size: 20 }),
      rect(860, 455, 300, 160, ["MemoryAnswer", "+ answer_id", "+ status", "+ citations"], { size: 20 }),
      rect(1240, 455, 300, 160, ["MemoryWorkflow", "+ workflow_id", "+ route", "+ status", "+ stop_reason"], { size: 20 }),
      rect(840, 730, 300, 140, ["WorkflowStep", "+ action", "+ input/output", "+ status"], { size: 20 }),
      rect(1200, 730, 300, 140, ["WorkflowRoute", "+ route", "+ reasons", "+ wants_external"], { size: 20 }),
      arrow(380, 240, 470, 240, "fetches"),
      arrow(770, 250, 860, 250, "recorded as"),
      arrow(1160, 250, 1240, 250, "aggregates"),
      arrow(380, 535, 470, 535, "restores into"),
      arrow(770, 535, 860, 535, "supports"),
      arrow(1160, 535, 1240, 535, "stored in"),
      arrow(1370, 615, 990, 730, "1..*", { open: true }),
      arrow(1370, 615, 1350, 730, "1", { open: true }),
    ].join("")),
  },
  {
    file: "06-activity-acquisition",
    title: "UML Activity: 取得から共有Storeまで",
    reason: "採用: provider chainと失敗分類の運用フローを説明するため。",
    svg: () => frame("UML Activity: 取得から共有Storeまで", [
      `<circle cx="140" cy="250" r="20" fill="${palette.line}"/>`,
      state(230, 205, 250, 90, ["targetを読む"]),
      state(560, 205, 270, 90, ["SessionBroker", "session materialize"]),
      state(910, 205, 280, 90, ["provider chain", "kind別に解決"]),
      state(910, 380, 280, 90, ["adapter.fetch()", "例外を隔離"]),
      state(560, 380, 270, 90, ["failure分類", "evidence JSON"]),
      state(230, 380, 250, 90, ["item merge", "dedupe / provider追跡"]),
      state(230, 570, 250, 90, ["十分な件数?"]),
      state(560, 570, 270, 90, ["JSONL / SQLiteへ保存"]),
      state(910, 570, 280, 90, ["pipeline report", "status出力"]),
      `<circle cx="1270" cy="615" r="24" fill="${palette.bg}" stroke="${palette.line}" stroke-width="3"/><circle cx="1270" cy="615" r="13" fill="${palette.line}"/>`,
      arrow(160, 250, 230, 250),
      arrow(480, 250, 560, 250),
      arrow(830, 250, 910, 250),
      arrow(1050, 295, 1050, 380),
      arrow(910, 425, 830, 425),
      arrow(560, 425, 480, 425),
      arrow(355, 470, 355, 570),
      arrow(480, 615, 560, 615, "yes"),
      arrow(830, 615, 910, 615),
      arrow(1190, 615, 1246, 615),
      curvedArrow("M355 570 C355 500 720 500 910 425", "no / next provider", 640, 520),
    ].join("")),
  },
  {
    file: "07-state-workflow",
    title: "UML State Machine: Memory Workflow",
    reason: "採用: stop_reasonとprovider gateで止まる状態を説明するため。",
    svg: () => frame("UML State Machine: Memory Workflow", [
      `<circle cx="130" cy="235" r="20" fill="${palette.line}"/>`,
      state(230, 190, 240, 90, ["planning", "route選択"]),
      state(570, 190, 250, 90, ["context", "local source復元"]),
      state(930, 190, 250, 90, ["llm_context", "承認時のみ"], { stroke: palette.red }),
      state(570, 410, 250, 90, ["answer", "承認時のみ"], { stroke: palette.red }),
      state(930, 410, 250, 90, ["needs_review", "不足/確認待ち"]),
      state(230, 410, 240, 90, ["ok", "enough_evidence"]),
      state(570, 650, 250, 90, ["provider_gated", "外部利用待ち"], { stroke: palette.red }),
      state(930, 650, 250, 90, ["error", "provider/error"]),
      `<circle cx="1325" cy="455" r="24" fill="${palette.bg}" stroke="${palette.line}" stroke-width="3"/><circle cx="1325" cy="455" r="13" fill="${palette.line}"/>`,
      arrow(150, 235, 230, 235),
      arrow(470, 235, 570, 235, "plan ok"),
      arrow(820, 235, 930, 235, "fresh/current"),
      arrow(695, 280, 695, 410, "answer requested"),
      arrow(570, 455, 470, 455, "citation ok"),
      arrow(820, 455, 930, 455, "citation_missing"),
      arrow(1055, 500, 1055, 650, "provider error"),
      arrow(695, 500, 695, 650, "no approval", { stroke: palette.red, dash: true }),
      arrow(1180, 455, 1301, 455),
      arrow(470, 455, 1301, 455),
    ].join("")),
  },
  {
    file: "08-sequence-memory-query",
    title: "UML Sequence: Memory query",
    reason: "採用: 1回の問い合わせでどの部品が順に動くかを示すため。",
    svg: () => frame("UML Sequence: Memory query", [
      sequenceParticipant(160, "SI/AI\nclient"),
      sequenceParticipant(380, "CLI"),
      sequenceParticipant(620, "Memory\nWorkflow"),
      sequenceParticipant(870, "Search /\nContext"),
      sequenceParticipant(1120, "SQLite\nDB"),
      sequenceParticipant(1370, "API Budget\nGuard"),
      activation(620, 270, 480),
      activation(870, 350, 200),
      activation(1120, 390, 150),
      arrow(160, 285, 380, 285, "memory workflow(query)"),
      arrow(380, 325, 620, 325, "run_memory_workflow"),
      arrow(620, 365, 870, 365, "build_context_bundle"),
      arrow(870, 405, 1120, 405, "search memory_documents / FTS"),
      arrow(1120, 455, 870, 455, "hits + source ids"),
      arrow(870, 520, 620, 520, "context chunks + citations"),
      arrow(620, 600, 1370, 600, "optional provider?", { stroke: palette.red, dash: true }),
      arrow(1370, 650, 620, 650, "block or approve", { stroke: palette.red, dash: true }),
      arrow(620, 725, 380, 725, "workflow_id/status/stop_reason"),
      arrow(380, 775, 160, 775, "answer or needs_review"),
      note(960, 760, 470, 95, ["回答が正しそうでもcitation-readyでなければ", "`needs_review` / `citation_missing` で止める。"]),
    ].join("")),
  },
];

async function loadSharp() {
  try {
    return createRequire(import.meta.url)("sharp");
  } catch {
    const nodePath = process.env.NODE_PATH;
    if (nodePath) {
      for (const candidate of nodePath.split(path.delimiter)) {
        try {
          return createRequire(path.join(candidate, "sharp", "package.json"))("sharp");
        } catch {
          // Continue probing NODE_PATH entries.
        }
      }
    }
  }
  return null;
}

async function writeManifest() {
  const selected = diagrams.map((diagram) => ({
    file: diagram.file,
    title: diagram.title,
    reason: diagram.reason,
    svg: `${diagram.file}.svg`,
    png: `${diagram.file}.png`,
  }));
  const manifest = {
    generated_by: "node scripts/uml/build-research-x-uml.mjs",
    purpose: "research_x SI事業者向けのUML説明図。スライドではなく単体SVG/PNG成果物。",
    selection_policy: [
      "8種類はUse Case, Component, Package, Deployment, Class, Activity, State Machine, Sequenceを採用。",
      "Object, Communication, Timing, Interaction Overview, Profile, Composite Structureは重複または過詳細のため除外。",
      "全図はreview/presentation artifactであり、answer evidenceではない。",
    ],
    selected,
    excluded: [
      { type: "Object", reason: "特定時点のインスタンス状態は現段階のSI説明ではClass/DB表で足りる。" },
      { type: "Communication", reason: "Sequence diagramと情報が重複し、読み手の負荷が増える。" },
      { type: "Timing", reason: "時間制約やリアルタイム挙動が主要論点ではない。" },
      { type: "Interaction Overview", reason: "Activity + Sequenceで十分に説明できる。" },
      { type: "Profile", reason: "UML拡張メタモデルは今回の引き継ぎ範囲外。" },
      { type: "Composite Structure", reason: "内部部品構成はComponent diagramで十分。" },
    ],
    web_sources: [
      "https://www.omg.org/spec/UML/2.5.1/About-UML",
      "https://www.uml-diagrams.org/uml-25-diagrams.html",
      "https://plantuml.com/",
      "https://www.atlassian.com/work-management/project-management/uml-diagram",
    ],
    local_sources: [
      "README.codex.md",
      "docs/memory-pipeline-v2.md",
      "docs/pipeline.md",
      "src/research_x/pipeline.py",
      "src/research_x/x_store.py",
      "src/research_x/memory/schema.py",
      "src/research_x/memory/workflow.py",
    ],
  };
  await writeFile(path.join(outDir, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
}

async function main() {
  await mkdir(outDir, { recursive: true });
  const sharp = await loadSharp();
  const rendered = [];
  for (const diagram of diagrams) {
    const svg = diagram.svg();
    const svgPath = path.join(outDir, `${diagram.file}.svg`);
    const pngPath = path.join(outDir, `${diagram.file}.png`);
    await writeFile(svgPath, svg, "utf8");
    if (sharp) {
      await sharp(Buffer.from(svg)).png().toFile(pngPath);
    }
    rendered.push({
      svg: path.relative(root, svgPath),
      png: sharp ? path.relative(root, pngPath) : null,
    });
  }
  await writeManifest();
  console.log(JSON.stringify({ ok: true, rendered, png: Boolean(sharp) }, null, 2));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exit(1);
});
