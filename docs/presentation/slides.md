---
marp: true
theme: default
paginate: true
size: 16:9
style: |
  section {
    color: #22313f;
    font-family: "Aptos", "Yu Gothic", "Meiryo", "Segoe UI", sans-serif;
    letter-spacing: 0;
    padding: 46px 64px;
  }
  h1 {
    color: #244766;
    font-size: 38px;
    margin-bottom: 16px;
  }
  h2 {
    color: #244766;
    font-size: 27px;
  }
  p, li {
    font-size: 20px;
    line-height: 1.38;
  }
  section.diagram img {
    display: block;
    margin: 16px auto 0;
    max-height: 455px;
    max-width: 96%;
  }
  .lead {
    font-size: 24px;
    line-height: 1.38;
    max-width: 880px;
  }
  .small {
    font-size: 17px;
    line-height: 1.36;
  }
  .two {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 28px;
  }
---

# research_x を5枚で見る

<!-- claim: claim-project-purpose -->
<!-- claim: claim-sier-context -->

<p class="lead">Xの投稿・ブックマーク・メディアを、AI agent がローカルで探せる形に整えるプロジェクトです。大事なのは、検索候補をそのまま根拠扱いしないことです。</p>

- 図は説明とレビューのためのものです
- 回答根拠になるのは、復元できる出典・文脈・引用だけです
- 外部Provider/APIを使う候補ルートは、承認と予算確認の後に進めます

---

# 1. 全体アーキテクチャ

<!-- claim: claim-runtime-architecture -->
<!-- claim: claim-c4-container-boundary -->
<!-- claim: claim-acquisition-chain -->
<!-- claim: claim-bookmark-store -->
<!-- _class: diagram -->

![全体アーキテクチャ](assets/c4-container.svg)

<p class="small">人、AI agent、開発者/運用者から見て、research_x がどこまでを担当し、どこから承認ゲートになるかを分けて見る。</p>

---

# 2. 証拠パイプライン

<!-- claim: claim-evidence-invariant -->
<!-- claim: claim-memory-schema -->
<!-- _class: diagram -->

![証拠パイプライン](assets/memory-evidence-flow.svg)

<p class="small">検索結果は候補です。Source Bundle へ戻せて、Context Chunk と Citation を作れて初めて、回答に使えます。</p>

---

# 3. 1回の memory query

<!-- claim: claim-workflow-execution -->
<!-- _class: diagram -->

![1回の memory query](assets/memory-query-sequence.svg)

<p class="small">1回の問い合わせは、検索方針、候補ルート、provider guard、出典復元、文脈化、引用、回答権限、Answer Boundary を分けて扱い、trace は横で記録する。</p>

---

# 4. provider / quota guard

<!-- claim: claim-provider-gate -->
<!-- claim: claim-sier-boundary -->
<!-- _class: diagram -->

![provider / quota guard](assets/runtime-boundary.svg)

<p class="small">fake/local provider、静的検査、monkeypatch済みテストは進められる。real API、Reader、OCR、外部検索、quota消費は ProviderApiBudgetGuard で止めて確認する。</p>

---

# 5. WBS / ロードマップ

<!-- claim: claim-current-open-items -->
<!-- claim: claim-control-artifacts -->
<!-- _class: diagram -->

![WBS / ロードマップ](assets/roadmap.svg)

<p class="small">現状の土台、次に固めること、承認後に進めることを混ぜない。図やPPTXは確認用であり、回答根拠ではない。</p>

---

# 読み方

<!-- claim: claim-dev-entrypoints -->

<div class="two">
<div>

## 初見で見る順番

1. 全体アーキテクチャ
2. 証拠パイプライン
3. 1回の memory query
4. provider / quota guard
5. WBS / ロードマップ

</div>
<div>

## 判断の基準

- 英語名は固有名だけ残す
- 抽象名より、何をする場所かを書く
- 矢印は主な流れだけに絞る
- 止まる条件を赤で見せる
- 図は根拠ではなく確認用

</div>
</div>
