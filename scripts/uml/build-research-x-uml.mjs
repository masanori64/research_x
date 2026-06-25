import { existsSync } from "node:fs";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const outDir = path.join(root, "docs", "uml");
const width = 1800;
const height = 1120;

const palette = {
  ink: "#1f2933",
  mutedInk: "#50606f",
  blue: "#1f4e79",
  blueSoft: "#edf4fb",
  cyanSoft: "#e8f7f6",
  greenSoft: "#edf7ed",
  amberSoft: "#fff8df",
  red: "#c62828",
  redSoft: "#fff0f0",
  line: "#234e8f",
  gray: "#eef2f6",
  bg: "#ffffff",
};

function esc(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function textLines(lines, x, y, opts = {}) {
  const size = opts.size ?? 22;
  const weight = opts.weight ?? 600;
  const color = opts.color ?? palette.ink;
  const anchor = opts.anchor ?? "middle";
  const gap = opts.gap ?? Math.round(size * 1.28);
  const tspans = lines
    .map((line, index) => `<tspan x="${x}" dy="${index === 0 ? 0 : gap}">${esc(line)}</tspan>`)
    .join("");
  return `<text x="${x}" y="${y}" font-size="${size}" font-weight="${weight}" text-anchor="${anchor}" fill="${color}">${tspans}</text>`;
}

function title(label, subtitle = "") {
  return [
    textLines([label], 74, 82, { size: 44, weight: 800, color: palette.blue, anchor: "start" }),
    subtitle
      ? textLines([subtitle], 78, 122, { size: 20, weight: 600, color: palette.mutedInk, anchor: "start" })
      : "",
  ].join("");
}

function rect(x, y, w, h, lines, opts = {}) {
  const fill = opts.fill ?? palette.blueSoft;
  const stroke = opts.stroke ?? palette.line;
  const rx = opts.rx ?? 6;
  const size = opts.size ?? 20;
  const gap = opts.gap ?? Math.round(size * 1.25);
  const top = y + h / 2 - ((lines.length - 1) * gap) / 2 + size * 0.35;
  return [
    `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${rx}" fill="${fill}" stroke="${stroke}" stroke-width="${opts.strokeWidth ?? 2}"/>`,
    textLines(lines, x + w / 2, top, { size, weight: opts.weight ?? 700, color: opts.color ?? palette.ink, gap }),
  ].join("");
}

function classBox(x, y, w, h, name, attrs = [], methods = [], opts = {}) {
  const headerH = opts.headerH ?? 46;
  const attrH = opts.attrH ?? Math.max(48, attrs.length * 25 + 20);
  const fill = opts.fill ?? "#fbfdff";
  const stroke = opts.stroke ?? palette.line;
  return [
    `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="0" fill="${fill}" stroke="${stroke}" stroke-width="2"/>`,
    `<rect x="${x}" y="${y}" width="${w}" height="${headerH}" rx="0" fill="${opts.headerFill ?? palette.blueSoft}" stroke="${stroke}" stroke-width="2"/>`,
    textLines([name], x + w / 2, y + 30, { size: 20, weight: 800 }),
    `<line x1="${x}" y1="${y + headerH + attrH}" x2="${x + w}" y2="${y + headerH + attrH}" stroke="${stroke}" stroke-width="2"/>`,
    ...attrs.map((line, index) =>
      textLines([line], x + 14, y + headerH + 30 + index * 25, {
        size: 17,
        weight: 600,
        anchor: "start",
      }),
    ),
    ...methods.map((line, index) =>
      textLines([line], x + 14, y + headerH + attrH + 28 + index * 25, {
        size: 17,
        weight: 600,
        anchor: "start",
        color: palette.mutedInk,
      }),
    ),
  ].join("");
}

function ellipse(x, y, w, h, lines, opts = {}) {
  const fill = opts.fill ?? palette.blueSoft;
  const stroke = opts.stroke ?? palette.line;
  const size = opts.size ?? 20;
  const gap = opts.gap ?? Math.round(size * 1.25);
  const top = y + h / 2 - ((lines.length - 1) * gap) / 2 + size * 0.35;
  return [
    `<ellipse cx="${x + w / 2}" cy="${y + h / 2}" rx="${w / 2}" ry="${h / 2}" fill="${fill}" stroke="${stroke}" stroke-width="2"/>`,
    textLines(lines, x + w / 2, top, { size, weight: 700, gap }),
  ].join("");
}

function actor(x, y, labelLines) {
  return [
    `<circle cx="${x}" cy="${y}" r="24" fill="${palette.bg}" stroke="${palette.line}" stroke-width="2"/>`,
    `<line x1="${x}" y1="${y + 24}" x2="${x}" y2="${y + 98}" stroke="${palette.line}" stroke-width="2"/>`,
    `<line x1="${x - 50}" y1="${y + 52}" x2="${x + 50}" y2="${y + 52}" stroke="${palette.line}" stroke-width="2"/>`,
    `<line x1="${x}" y1="${y + 98}" x2="${x - 48}" y2="${y + 160}" stroke="${palette.line}" stroke-width="2"/>`,
    `<line x1="${x}" y1="${y + 98}" x2="${x + 48}" y2="${y + 160}" stroke="${palette.line}" stroke-width="2"/>`,
    textLines(labelLines, x, y + 205, { size: 20, weight: 800, gap: 26 }),
  ].join("");
}

function packageBox(x, y, w, h, name, lines = [], opts = {}) {
  const stroke = opts.stroke ?? palette.line;
  const fill = opts.fill ?? "#fbfdff";
  const tabW = Math.min(190, w * 0.48);
  return [
    `<path d="M${x} ${y + 34} L${x} ${y + h} L${x + w} ${y + h} L${x + w} ${y + 34} L${x + tabW} ${y + 34} L${x + tabW - 24} ${y} L${x} ${y} Z" fill="${fill}" stroke="${stroke}" stroke-width="2"/>`,
    textLines([name], x + 18, y + 25, { size: 18, weight: 800, anchor: "start" }),
    ...lines.map((line, index) =>
      textLines([line], x + 22, y + 74 + index * 30, {
        size: 18,
        weight: 600,
        anchor: "start",
        color: palette.ink,
      }),
    ),
  ].join("");
}

function state(x, y, w, h, lines, opts = {}) {
  return rect(x, y, w, h, lines, {
    fill: opts.fill ?? palette.blueSoft,
    stroke: opts.stroke ?? palette.line,
    rx: 18,
    size: opts.size ?? 19,
    weight: 700,
  });
}

function note(x, y, w, h, lines, opts = {}) {
  return rect(x, y, w, h, lines, {
    fill: opts.fill ?? palette.amberSoft,
    stroke: opts.stroke ?? "#b08900",
    rx: 4,
    size: opts.size ?? 18,
    weight: 650,
  });
}

function arrow(x1, y1, x2, y2, label = "", opts = {}) {
  const stroke = opts.stroke ?? palette.line;
  const dash = opts.dash ? ' stroke-dasharray="10 8"' : "";
  const marker = opts.open ? "url(#openArrow)" : "url(#arrow)";
  const labelSvg = label
    ? textLines([label], (x1 + x2) / 2, (y1 + y2) / 2 - 10, {
        size: opts.labelSize ?? 17,
        weight: 700,
        color: stroke,
      })
    : "";
  return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${stroke}" stroke-width="${opts.strokeWidth ?? 2.4}"${dash} marker-end="${marker}"/>${labelSvg}`;
}

function curvedArrow(d, label = "", x = 0, y = 0, opts = {}) {
  const stroke = opts.stroke ?? palette.line;
  const dash = opts.dash ? ' stroke-dasharray="10 8"' : "";
  return [
    `<path d="${d}" fill="none" stroke="${stroke}" stroke-width="${opts.strokeWidth ?? 2.4}"${dash} marker-end="url(#arrow)"/>`,
    label
      ? textLines([label], x, y, { size: opts.labelSize ?? 17, weight: 700, color: stroke })
      : "",
  ].join("");
}

function participant(x, label) {
  return [
    rect(x - 95, 154, 190, 66, label, { size: 17, fill: "#fbfdff" }),
    `<line x1="${x}" y1="220" x2="${x}" y2="930" stroke="#8798a8" stroke-width="2" stroke-dasharray="8 8"/>`,
  ].join("");
}

function activation(x, y, h) {
  return `<rect x="${x - 10}" y="${y}" width="20" height="${h}" fill="#dce8f4" stroke="${palette.line}" stroke-width="1.5"/>`;
}

function frame(diagramName, subtitle, body) {
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
<defs>
  <marker id="arrow" markerWidth="13" markerHeight="13" refX="11" refY="6.5" orient="auto"><path d="M0,0 L13,6.5 L0,13 Z" fill="${palette.line}"/></marker>
  <marker id="openArrow" markerWidth="14" markerHeight="14" refX="12" refY="7" orient="auto"><path d="M1,1 L13,7 L1,13" fill="none" stroke="${palette.line}" stroke-width="2"/></marker>
  <style>
    text { font-family: "Yu Gothic", "Meiryo", "Noto Sans CJK JP", "Aptos", "Segoe UI", sans-serif; }
  </style>
</defs>
<rect width="100%" height="100%" fill="${palette.bg}"/>
${title(diagramName, subtitle)}
${body}
</svg>`;
}

const diagrams = [
  {
    file: "01-use-case",
    title: "UMLユースケース図：research_x の利用場面",
    reason: "採用: 利用者、AIエージェント、開発者、承認者の責務を1枚で確認するため。",
    svg: () =>
      frame(
        "UMLユースケース図：research_x の利用場面",
        "誰が、どの境界で、何を実行・確認・承認するか",
        [
          actor(140, 255, ["利用者"]),
          actor(140, 620, ["AI", "エージェント"]),
          actor(1660, 255, ["開発者"]),
          actor(1660, 620, ["承認者"]),
          `<rect x="300" y="165" width="1200" height="770" rx="10" fill="#fbfdff" stroke="#7b8da0" stroke-width="2"/>`,
          textLines(["research_x ローカル記憶検索システム"], 900, 214, {
            size: 27,
            weight: 850,
            color: palette.blue,
          }),
          ellipse(370, 285, 300, 96, ["Xデータを取得", "認証状態を準備"]),
          ellipse(740, 285, 320, 96, ["共有保存へ記録", "重複と引用関係を統合"]),
          ellipse(1130, 285, 300, 96, ["コーパスを再構築", "検索文書を生成"]),
          ellipse(380, 480, 320, 96, ["ローカル検索", "全文検索・属性・関係"]),
          ellipse(760, 480, 330, 96, ["ソース束を復元", "投稿・メディア・引用"]),
          ellipse(1160, 480, 330, 96, ["文脈チャンク作成", "引用候補を付与"]),
          ellipse(565, 685, 330, 96, ["引用付き回答", "不足時は保留"]),
          ellipse(965, 685, 330, 96, ["実行履歴監査", "状態と停止理由を確認"]),
          ellipse(1245, 770, 300, 96, ["外部API承認", "予算ガードを通す"], {
            fill: palette.redSoft,
            stroke: palette.red,
          }),
          arrow(220, 325, 370, 320),
          arrow(220, 680, 390, 515),
          arrow(220, 680, 565, 730),
          arrow(1530, 345, 1432, 333),
          arrow(1530, 680, 1370, 815, "承認", { stroke: palette.red }),
          arrow(670, 333, 740, 333),
          arrow(1060, 333, 1130, 333),
          arrow(700, 528, 760, 528),
          arrow(1090, 528, 1160, 528),
          arrow(710, 653, 650, 685),
          arrow(1010, 576, 990, 685),
          arrow(1230, 576, 1280, 770, "外部利用時のみ", { stroke: palette.red, dash: true }),
          note(560, 875, 680, 55, ["図は確認用。回答根拠はソース束・文脈チャンク・引用で確認する。"], {
            size: 18,
          }),
        ].join(""),
      ),
  },
  {
    file: "02-component",
    title: "UMLコンポーネント図：主要部品と責務境界",
    reason: "採用: 実装部品、保存境界、外部APIゲート、確認成果物の関係を俯瞰するため。",
    svg: () =>
      frame(
        "UMLコンポーネント図：主要部品と責務境界",
        "外部呼び出しをせずに確認できるローカル構成を中心に置く",
        [
          rect(80, 190, 250, 88, ["<<部品>>", "コマンド入口"], { fill: "#fbfdff" }),
          rect(430, 155, 285, 92, ["<<部品>>", "認証・セッション", "Cookieを整える"], {
            fill: palette.greenSoft,
            size: 18,
          }),
          rect(430, 310, 285, 92, ["<<部品>>", "取得パイプライン", "取得部品を順に試す"], {
            fill: palette.greenSoft,
            size: 18,
          }),
          rect(820, 240, 300, 92, ["<<部品>>", "取得部品カタログ", "X取得の候補群"], {
            fill: palette.greenSoft,
            size: 18,
          }),
          rect(1260, 240, 310, 92, ["<<外部>>", "X・Web・外部API", "承認なし実行禁止"], {
            fill: palette.redSoft,
            stroke: palette.red,
            size: 18,
          }),
          rect(430, 500, 285, 92, ["<<データベース>>", "共有X保存", "投稿・ブックマーク・メディア"], {
            fill: palette.cyanSoft,
            size: 18,
          }),
          rect(820, 500, 300, 92, ["<<部品>>", "記憶コーパス構築", "検索文書・関係"], {
            fill: palette.cyanSoft,
            size: 18,
          }),
          rect(1260, 500, 310, 92, ["<<部品>>", "検索・文脈作成", "束・チャンク・引用"], {
            fill: palette.cyanSoft,
            size: 18,
          }),
          rect(820, 700, 300, 92, ["<<部品>>", "実行履歴・回答", "状態と停止理由"], {
            fill: palette.blueSoft,
            size: 18,
          }),
          rect(1260, 700, 310, 92, ["<<部品>>", "API予算ガード", "外部実行前に停止"], {
            fill: palette.redSoft,
            stroke: palette.red,
            size: 18,
          }),
          rect(430, 760, 285, 92, ["<<部品>>", "確認成果物", "WBS・図・目録"], {
            fill: palette.amberSoft,
            size: 18,
          }),
          arrow(330, 235, 430, 205),
          arrow(330, 235, 430, 356),
          arrow(715, 356, 820, 286),
          arrow(1120, 286, 1260, 286, "要承認", { stroke: palette.red, dash: true }),
          arrow(572, 402, 572, 500),
          arrow(715, 546, 820, 546),
          arrow(1120, 546, 1260, 546),
          arrow(970, 592, 970, 700),
          arrow(1120, 746, 1260, 746, "外部必要時", { stroke: palette.red, dash: true }),
          arrow(715, 806, 820, 746, "確認", { dash: true }),
          note(120, 910, 590, 80, ["確認成果物は進行・確認用。", "ソース束や引用の代替にはしない。"]),
        ].join(""),
      ),
  },
  {
    file: "03-package",
    title: "UMLパッケージ図：コード配置と依存の読み順",
    reason: "採用: 初見でどのPython/Node領域を読めばよいかを示すため。",
    svg: () =>
      frame(
        "UMLパッケージ図：コード配置と依存の読み順",
        "実装面の入口・取得・保存・記憶検索・確認成果物を分けて見る",
        [
          packageBox(90, 180, 330, 180, "コマンド入口", ["起動窓口", "引数と安全ゲート", "uv実行前提"]),
          packageBox(525, 150, 360, 200, "認証・セッション", [
            "account別path",
            "セッション変換",
            ".secretsは非公開",
          ]),
          packageBox(1010, 150, 360, 220, "取得部品", [
            "部品カタログ",
            "X取得ライブラリ",
            "ブラウザ代替",
            "失敗分類",
          ]),
          packageBox(525, 445, 360, 190, "取得処理", [
            "取得部品の順序",
            "証拠JSON",
            "対象ごとの結果",
          ]),
          packageBox(1010, 445, 360, 190, "共有保存", [
            "投稿",
            "ブックマーク",
            "引用関係・メディア",
          ]),
          packageBox(525, 745, 400, 225, "記憶検索", [
            "表定義・コーパス",
            "検索・文脈",
            "回答・実行履歴",
            "予算・評価・監査",
          ]),
          packageBox(1010, 760, 360, 190, "発表・確認成果物", [
            "図・スライド確認",
            "目録・検証",
            "証拠ではない",
          ]),
          packageBox(90, 760, 330, 190, "テスト", ["境界テスト", "UML資産", "外部利用停止"]),
          arrow(420, 245, 525, 245),
          arrow(885, 260, 1010, 260),
          arrow(705, 350, 705, 445),
          arrow(885, 540, 1010, 540),
          arrow(705, 635, 705, 745),
          arrow(925, 855, 1010, 855, "確認成果物", { dash: true }),
          arrow(420, 855, 525, 855, "検証"),
          curvedArrow("M255 760 C260 610 390 520 525 520", "取得処理テスト", 355, 610, { dash: true }),
          note(1420, 780, 280, 140, ["図の正本はコードではなく、", "確認用生成物。", "設計境界は文書とテストで検証する。"], {
            size: 17,
          }),
        ].join(""),
      ),
  },
  {
    file: "04-deployment",
    title: "UML配置図：ローカル実行と外部ゲート",
    reason: "採用: ローカルファイル、データベース、ブラウザ、外部APIの実行境界を明確にするため。",
    svg: () =>
      frame(
        "UML配置図：ローカル実行と外部ゲート",
        "外部API凍結中はローカル確認だけで閉じる",
        [
          `<rect x="80" y="175" width="520" height="740" rx="6" fill="#fbfdff" stroke="${palette.line}" stroke-width="2"/>`,
          textLines(["<<ノード>> ローカル作業PC"], 115, 220, {
            size: 23,
            weight: 800,
            anchor: "start",
            color: palette.blue,
          }),
          rect(145, 285, 390, 90, ["Python + uv", "コマンドとテスト"], { fill: palette.blueSoft }),
          rect(145, 420, 390, 90, ["SQLite データベース", "runs/x_data.sqlite3"], { fill: palette.cyanSoft }),
          rect(145, 555, 390, 90, ["ファイルシステム", "runs / docs / outputs"], { fill: palette.cyanSoft }),
          rect(145, 690, 390, 90, ["秘密情報", ".secrets / アカウントCookie"], {
            fill: palette.redSoft,
            stroke: palette.red,
          }),
          rect(705, 205, 405, 150, ["<<実行環境>>", "ブラウザ実行", "取得と代替経路"], {
            fill: palette.greenSoft,
            size: 20,
          }),
          rect(705, 455, 405, 150, ["<<データベース>>", "記憶検索表", "全文検索・文脈・引用・履歴"], {
            fill: palette.cyanSoft,
            size: 20,
          }),
          rect(705, 710, 405, 150, ["<<実行環境>>", "Node図表ツール", "UML画像・図表・発表資料"], {
            fill: palette.amberSoft,
            size: 20,
          }),
          rect(1260, 240, 380, 150, ["<<外部ノード>>", "X・公開Web", "取得・読取は承認が必要"], {
            fill: palette.redSoft,
            stroke: palette.red,
            size: 20,
          }),
          rect(1260, 560, 380, 150, ["<<外部ノード>>", "生成AI・埋め込み・再順位付け", "予算ガード通過後のみ"], {
            fill: palette.redSoft,
            stroke: palette.red,
            size: 20,
          }),
          arrow(535, 330, 705, 280),
          arrow(535, 465, 705, 530),
          arrow(535, 600, 705, 785),
          arrow(1110, 280, 1260, 315, "要承認", { stroke: palette.red, dash: true }),
          arrow(1110, 530, 1260, 635, "要承認", { stroke: palette.red, dash: true }),
          note(1170, 815, 470, 95, ["配置図は権限を与えない。", "外部実行はAGENTS.mdとAPI予算ガードで止める。"]),
        ].join(""),
      ),
  },
  {
    file: "05-class-core",
    title: "UMLクラス図：中核データと証拠オブジェクト",
    reason: "採用: 型、データベース投影、ソース復元、文脈、引用、回答の対応を確認するため。",
    svg: () =>
      frame(
        "UMLクラス図：中核データと証拠オブジェクト",
        "生ソースから回答まで同一物扱いしないための構造",
        [
          classBox(70, 160, 315, 210, "取得対象", ["種別", "値", "上限"], ["取得対象"]),
          classBox(455, 160, 315, 230, "取得項目", ["取得元ID", "URL", "本文", "生データ"], [
            "正規化された取得項目",
          ]),
          classBox(840, 160, 315, 220, "取得結果", ["取得部品ID", "状態", "項目群", "エラー"], [
            "取得部品の結果",
          ]),
          classBox(1225, 160, 400, 230, "共有保存表", [
            "投稿",
            "ブックマーク",
            "収集項目",
            "引用関係・メディア",
          ], ["生ソースの土台"], { headerFill: palette.cyanSoft }),
          classBox(70, 470, 355, 210, "検索候補", ["文書ID", "文書種別", "順位点", "付加情報"], [
            "検索結果は候補",
          ]),
          classBox(505, 470, 355, 210, "文脈束", ["取得候補", "文脈チャンク", "引用注釈"], [
            "回答入力の束",
          ]),
          classBox(940, 470, 355, 210, "文脈チャンク", ["ソース種別", "ソースID", "チャンク本文", "付加情報"], [
            "ソース束由来",
          ]),
          classBox(1375, 470, 355, 210, "引用注釈", [
            "チャンクID",
            "対象位置",
            "証拠状態",
            "信頼度",
          ], ["根拠注釈"], { headerFill: palette.greenSoft }),
          classBox(505, 760, 355, 205, "実行ワークフロー", ["履歴ID", "状態", "停止理由", "手順"], [
            "実行状態",
          ]),
          classBox(940, 760, 355, 205, "記憶回答", ["回答ID", "状態", "回答本文", "引用"], [
            "正しそうでも引用必須",
          ]),
          arrow(385, 255, 455, 255),
          arrow(770, 255, 840, 255),
          arrow(1155, 255, 1225, 255),
          curvedArrow("M1425 390 C1320 430 530 430 250 470", "コーパス再構築", 850, 425, { dash: true }),
          arrow(425, 565, 505, 565, "復元"),
          arrow(860, 565, 940, 565, "分割"),
          arrow(1295, 565, 1375, 565, "注釈"),
          arrow(682, 680, 682, 760, "保存"),
          arrow(1117, 680, 1117, 760, "支える"),
          arrow(940, 855, 860, 855, "履歴が保持", { open: true }),
          note(120, 995, 760, 82, [
            "不変条件:",
            "生ソース != 検索文書 != 検索候補 != ソース束",
            "ソース束 != 文脈チャンク != 引用 != 回答",
          ], {
            size: 17,
          }),
        ].join(""),
      ),
  },
  {
    file: "06-activity-acquisition",
    title: "UMLアクティビティ図：X取得から共有保存まで",
    reason: "採用: 取得部品の順序、失敗分類、保存、次段の記憶構築への接続を確認するため。",
    svg: () =>
      frame(
        "UMLアクティビティ図：X取得から共有保存まで",
        "取得は生の証拠の入口。ラベルや要約で置き換えない",
        [
          `<circle cx="125" cy="235" r="22" fill="${palette.line}"/>`,
          state(220, 190, 285, 90, ["取得対象を読む", "プロフィール・検索・URL・保存済み"]),
          state(610, 190, 300, 90, ["セッションを準備", "アカウント別Cookie"]),
          state(1015, 190, 310, 90, ["取得部品の順序を選ぶ", "対象種別ごとの順序"]),
          state(1015, 365, 310, 90, ["取得部品を実行", "失敗を隔離"]),
          state(610, 365, 300, 90, ["失敗分類", "時間切れ・認証・構造変化等"]),
          state(220, 365, 285, 90, ["取得項目を統合", "重複と引用関係を整理"]),
          state(220, 560, 285, 90, ["十分な件数?", "カーソル終了も確認"]),
          state(610, 560, 300, 90, ["共有保存へ記録", "SQLiteとJSONL"]),
          state(1015, 560, 310, 90, ["試行記録", "取得試行ごとに記録"]),
          state(610, 755, 300, 90, ["記憶構築へ渡す", "投影は再構築可能"]),
          `<circle cx="1375" cy="605" r="25" fill="${palette.bg}" stroke="${palette.line}" stroke-width="3"/><circle cx="1375" cy="605" r="13" fill="${palette.line}"/>`,
          arrow(147, 235, 220, 235),
          arrow(505, 235, 610, 235),
          arrow(910, 235, 1015, 235),
          arrow(1170, 280, 1170, 365),
          arrow(1015, 410, 910, 410),
          arrow(610, 410, 505, 410),
          arrow(362, 455, 362, 560),
          arrow(505, 605, 610, 605, "はい"),
          arrow(910, 605, 1015, 605),
          arrow(1325, 605, 1350, 605),
          arrow(760, 650, 760, 755),
          curvedArrow("M362 560 C360 505 760 505 1015 410", "不足 / 次の取得部品", 675, 520),
          note(1180, 760, 430, 92, ["分類・記録は確認用。", "投稿・メディア・関係の保存が後段の証拠復元の土台。"]),
        ].join(""),
      ),
  },
  {
    file: "07-state-workflow",
    title: "UML状態機械図：メモリ実行履歴の停止理由",
    reason: "採用: 外部APIゲート、引用不足、レビュー待ち、成功状態を明確にするため。",
    svg: () =>
      frame(
        "UML状態機械図：メモリ実行履歴の停止理由",
        "正しそうな文章より、状態と停止理由を先に見る",
        [
          `<circle cx="120" cy="235" r="22" fill="${palette.line}"/>`,
          state(220, 190, 270, 90, ["計画中", "クエリ計画・経路"]),
          state(590, 190, 290, 90, ["ローカル文脈", "検索とソース復元"]),
          state(985, 190, 300, 90, ["引用確認", "文脈チャンクを確認"]),
          state(1370, 190, 300, 90, ["回答可能", "引用付き回答"], { fill: palette.greenSoft }),
          state(590, 430, 290, 90, ["レビュー待ち", "不足・矛盾・曖昧"], { fill: palette.amberSoft }),
          state(985, 430, 300, 90, ["外部保留", "外部文脈・API待ち"], {
            fill: palette.redSoft,
            stroke: palette.red,
          }),
          state(1370, 430, 300, 90, ["停止・エラー", "予算・外部API・実行失敗"], {
            fill: palette.redSoft,
            stroke: palette.red,
          }),
          state(220, 670, 270, 90, ["回答保留", "根拠不足を返す"], { fill: palette.amberSoft }),
          state(590, 670, 290, 90, ["監査履歴", "手順を保存"], { fill: palette.cyanSoft }),
          `<circle cx="1515" cy="780" r="25" fill="${palette.bg}" stroke="${palette.line}" stroke-width="3"/><circle cx="1515" cy="780" r="13" fill="${palette.line}"/>`,
          arrow(142, 235, 220, 235),
          arrow(490, 235, 590, 235, "経路決定"),
          arrow(880, 235, 985, 235, "ソース復元"),
          arrow(1285, 235, 1370, 235, "引用確認済み"),
          arrow(1135, 280, 1135, 430, "外部が必要", { stroke: palette.red, dash: true }),
          arrow(1285, 475, 1370, 475, "呼出失敗・予算"),
          arrow(985, 475, 880, 475, "承認なし", { stroke: palette.red, dash: true }),
          arrow(735, 280, 735, 430, "ソース不足"),
          arrow(590, 475, 490, 715, "回答不可"),
          arrow(735, 520, 735, 670, "履歴保存"),
          arrow(1520, 280, 1520, 755),
          arrow(880, 715, 1490, 780, "完了状態も履歴で確認", { dash: true }),
          note(985, 820, 500, 96, [
            "主な停止理由:",
            "十分な根拠 / ローカル根拠なし / 外部文脈待ち",
            "レビュー待ち / 予算超過 / 外部API失敗",
          ], {
            size: 17,
          }),
        ].join(""),
      ),
  },
  {
    file: "08-sequence-memory-query",
    title: "UMLシーケンス図：1回のメモリ検索",
    reason: "採用: 問い合わせ1回でコマンド入口、実行履歴、検索、データベース、予算ガードがどう連動するかを見るため。",
    svg: () =>
      frame(
        "UMLシーケンス図：1回のメモリ検索",
        "検索結果をそのまま回答根拠にしない順序を明示する",
        [
          participant(150, ["利用者 /", "AIエージェント"]),
          participant(370, ["コマンド", "入口"]),
          participant(610, ["メモリ", "実行履歴"]),
          participant(860, ["クエリ", "経路判断"]),
          participant(1110, ["検索", "文脈作成"]),
          participant(1360, ["SQLite", "データベース"]),
          participant(1610, ["予算", "ガード"]),
          activation(610, 285, 540),
          activation(860, 335, 120),
          activation(1110, 455, 210),
          activation(1360, 500, 120),
          arrow(150, 300, 370, 300, "メモリ検索要求"),
          arrow(370, 345, 610, 345, "実行履歴開始"),
          arrow(610, 390, 860, 390, "クエリ計画作成"),
          arrow(860, 440, 610, 440, "経路と制約"),
          arrow(610, 485, 1110, 485, "文脈束を作成"),
          arrow(1110, 530, 1360, 530, "検索文書 / 全文検索 / 関係"),
          arrow(1360, 590, 1110, 590, "候補一致 + ソースID"),
          arrow(1110, 650, 610, 650, "文脈チャンク + 引用"),
          arrow(610, 720, 1610, 720, "外部APIが必要?", { stroke: palette.red, dash: true }),
          arrow(1610, 770, 610, 770, "停止 / 承認", { stroke: palette.red, dash: true }),
          arrow(610, 845, 370, 845, "状態 + 停止理由 + 回答候補"),
          arrow(370, 900, 150, 900, "回答 / レビュー待ち / 外部保留"),
          note(1030, 840, 520, 90, ["検索一致は候補。", "ソース復元と引用確認を通って初めて回答入力になる。"]),
        ].join(""),
      ),
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

function browserCandidates() {
  const candidates = [
    process.env.RESEARCH_X_UML_BROWSER,
    process.env.EDGE_PATH,
    process.env.CHROME_PATH,
    process.platform === "win32"
      ? path.join(process.env["ProgramFiles(x86)"] || "C:\\Program Files (x86)", "Microsoft", "Edge", "Application", "msedge.exe")
      : null,
    process.platform === "win32"
      ? path.join(process.env.ProgramFiles || "C:\\Program Files", "Google", "Chrome", "Application", "chrome.exe")
      : null,
    "msedge",
    "google-chrome",
    "chromium",
    "chrome",
  ].filter(Boolean);
  return [...new Set(candidates)];
}

async function renderPng(svg, svgPath, pngPath, sharp) {
  await rm(pngPath, { force: true }).catch(() => {});
  if (sharp) {
    await sharp(Buffer.from(svg)).png().toFile(pngPath);
    return "sharp";
  }

  for (const executablePath of browserCandidates()) {
    if (path.isAbsolute(executablePath) && !existsSync(executablePath)) {
      continue;
    }
    const userDataDir = await mkdtemp(path.join(os.tmpdir(), "research-x-uml-edge-"));
    try {
      const result = spawnSync(
        executablePath,
        [
          "--headless",
          "--disable-gpu",
          "--no-first-run",
          "--no-default-browser-check",
          "--disable-extensions",
          "--hide-scrollbars",
          `--user-data-dir=${userDataDir}`,
          `--window-size=${width},${height}`,
          `--screenshot=${pngPath}`,
          pathToFileURL(svgPath).href,
        ],
        { encoding: "utf8", stdio: "pipe" },
      );
      if (result.status === 0 && existsSync(pngPath)) {
        return executablePath;
      }
    } finally {
      await rm(userDataDir, { recursive: true, force: true }).catch(() => {});
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
    purpose: "research_x全体の仕組みを日本語で確認するためのUML説明図。単体SVG/PNG成果物であり、回答根拠ではない。",
    created_for: "プロジェクト全体UML図の一からの作り直し",
    route_applied: [
      "research-x-implementation-plan-flow: 計画作成ではなく、入力境界・ローカル優先・停止ゲート・完了条件の確認に使用。",
      "ian-xiaohei-illustrations: 図の視覚設計メモとして追加使用。画像生成や証拠扱いはしない。",
    ],
    selection_policy: [
      "採用: ユースケース、コンポーネント、パッケージ、配置、クラス、アクティビティ、状態機械、シーケンスの8種類。",
      "目的: 利用場面、責務、コード配置、実行境界、データ構造、取得手順、実行状態、問い合わせ順序を別々に確認する。",
      "全図は確認・発表用の成果物であり、ソース束、文脈チャンク、引用、回答根拠ではない。",
      "外部API、読取、埋め込み、再順位付け、生成AI、外部検索の実行許可を図から与えない。",
    ],
    selected,
    excluded: [
      { type: "Object", reason: "特定時点のインスタンス例は現段階ではクラス図とDB表の説明で足りる。" },
      { type: "Communication", reason: "シーケンス図と重複し、部品間メッセージの理解に追加価値が少ない。" },
      { type: "Timing", reason: "リアルタイム制約よりも証拠境界と停止理由が主要論点。" },
      { type: "Interaction Overview", reason: "アクティビティ図とシーケンス図で十分に分解できる。" },
      { type: "Profile", reason: "UML拡張メタモデルはこの確認成果物の範囲外。" },
      { type: "Composite Structure", reason: "内部部品構造はコンポーネント図で十分に確認できる。" },
    ],
    xiaohei_visual_brief: {
      concept: "証拠の階段、赤い外部ゲート、ローカル作業台を反復モチーフにし、UMLでも説明図として読める密度にする。",
      shot_list: [
        "生ソースから回答までを同一物扱いしない階段構図",
        "外部APIを赤い門として表示し、承認なしには通過しない構図",
        "ローカルPC上のデータベース・ファイル・ブラウザ・図表生成を1つの作業台として見せる構図",
      ],
      evidence_boundary: "この視覚メモは説明補助であり、生成画像・図・目録を引用や回答根拠として扱わない。",
    },
    local_sources: [
      "README.codex.md",
      "PROJECT.md",
      "docs/memory-pipeline-v2.md",
      "docs/pipeline.md",
      "src/research_x/contracts.py",
      "src/research_x/pipeline.py",
      "src/research_x/x_store.py",
      "src/research_x/memory/schema.py",
      "src/research_x/memory/context.py",
      "src/research_x/memory/answer.py",
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
    const pngRenderer = await renderPng(svg, svgPath, pngPath, sharp);
    rendered.push({
      svg: path.relative(root, svgPath),
      png: pngRenderer ? path.relative(root, pngPath) : null,
      png_renderer: pngRenderer,
    });
  }

  await writeManifest();
  console.log(JSON.stringify({ ok: true, rendered }, null, 2));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exit(1);
});
