<!-- Historical consultation capture. Active path: README.md, tools/wbs_viewer/projects/research-x-work-state.json, and .codex/context_offloads/pointer-map.json. Retired diagram-tool notes inside are closed/reference-only. Not evidence; do not update as an active tracker. -->

## 前提

追加調査は、アップロードされた `Project Usability Review` の未解決・保留判定を対象にし、X/ChatGPT要約ではなく、Webで確認できた一次情報・公式情報・論文・GitHub・コミュニティ反応を基準に再判定しました。

結論として、**昇格しない理由が不透明なまま残るものはかなり減りました**。ただし、Ontology mention と Devin/Manus mention は、元投稿文脈自体が薄く、プロジェクト候補としては引き続き `not-actionable` です。

## 1. 再調査対象 / 除外対象

### 再調査対象にしたもの

| group | candidates |
| --- | --- |
| 明示重点候補 | Agentmemory / Hanno-Lab Bosun relevance model / JAMEL / Stale observation masking / RAG Knowledge Hub / Visual Skills / WBS Viewer / Ontology mention / Devin-Manus mention / YAML-to-HTML |
| reference-only 理由が薄い可能性があったもの | Archify / Ponytail / pdgkit |
| 既に有望だが未昇格理由を再点検したもの | OCC-RAG / Zvec / SkillAdaptor |

### 除外したもの

| excluded | reason |
| --- | --- |
| Firecrawl Keyless / Google Agentic RAG / Bedrock AgentCore / hosted RAG/search providers | provider-gated理由が透明。外部API、クラウド、課金、IAM、データ保持、quotaが主ブロッカー。今回は優先度を下げてよい対象。 |
| LLM-Oriented IR / SAAS / VS Code token efficiency | 既に use-now / use-now-narrow としてチェックリスト・メトリクス用途が明確で、昇格保留ではない。 |
| AI code review split / /grill-me / plan parallel review / decision rules as Markdown | 既存の人間レビュー・decision-loop・AGENTS/Skill面に吸収済みで、外部依存昇格候補ではない。 |
| MUSE-Autoskill / Adaptive Auto-Harness / harness overgrowth | Codex foundation設計入力としての位置づけが既に透明。インストール・実装対象ではなく、Skill governanceの参考。 |

## 2. 対象別更新表

| candidate | current verdict | opaque point / unresolved reason | sources checked | community / practical signal | updated project-use verdict | why not promote now | exact promotion condition / next evidence needed | Codex surface |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Agentmemory | skill-source-review-required | hooks/MCP/plugin導入、データ保持、既存memory面との重複がどこまで問題か不透明だった | GitHubはCodex CLI等を含む多数agent対応、hooks/MCP/REST、local server、benchmark、token savingsを主張。実装は自動capture・検索・inject型。GitHub | GitHub上のstar/fork/issue/PR数は大きく、実用関心は強い。benchmarkはLongMemEval-S等を掲げるが、自前・比較条件差を含む。GitHub | 据え置き：skill-source-review-required | memory server、MCP、plugin、lifecycle hooks、raw tool observation captureが入る。research_xの既存memory/handoff/source-bundle設計に対して侵襲が大きい。 | pinned version、hook manifest精査、zero-network/local-only確認、削除/retention/secret redaction方針、既存memory baselineとの再現evalで勝つこと。 | 何もしない now。将来は MCP/plugin だが、現時点では不可。 |
| Hanno-Lab Bosun relevance model | source-intake-only | 元Xではモデル名不明。RAG関連性判定に使えるのか不明だった | Bosunは「instruction付きの関係/関連性judge」で、Bosun-XS 0.6B / Bosun-4B、WarrantBench、score=sigmoid(logit_yes-logit_no) の形。RAG filtering、dedup、memory graph clean-upにも言及。Hugging Face GGUF版はCPU/Apple Silicon/edge向けに公開。Hugging Face | WarrantBenchは2,000行規模でsteerability等を測る。Bosun-XSはrule flip系で強い結果を示すが、RAG/citation supportそのものの独立benchmarkではない。Hugging Face | 上方修正：source-intake-only → local-eval-candidate | RAG chunk relevance / citation support / conflict detection でのproject実測が未実施。公式blog自体も「何をtested / not testedか」を分けており、RAG実運用性能は未確定。 | Bosun-XS GGUFをlocalで走らせ、source-bundle relevance、citation-support、duplicate/conflict fixtureで既存rerank/sufficiency gateを上回る。threshold calibration必須。 | rule/local model checker。Skill/plugin/MCPではない。 |
| JAMEL | source-intake-only | GUI探索memoryとして面白いが、research_x用途との接続が薄かった | 論文はGUI領域でnovelty signal、特にcode coverageを使い、latent memoryとexploration policyを共同学習。24k samples / 86 appsで訓練、10 held-out appsで評価。arXiv | GitHubはあるが、実用導入というより研究実装。JAMEL-9BはGUI探索・学習前提で、通常の文書RAGとは別物。 | 据え置き：source-intake-only | 現在のresearch_xはsource intake / memory evidence中心。GUI/browser探索objective、coverage計測、訓練ランタイムがない。 | GUI/browser探索タスクを明示し、coverage/novelty metricをlocalで取得できるscaffoldを用意。JAMEL方式のmemory圧縮が履歴要約より勝つこと。 | 何もしない now。将来はGUI eval rule。 |
| Stale observation masking | source-intake-only | 「古い観察を隠す」べきか、いつ効くかが曖昧だった | 論文は4B〜284Bのagent backboneと3 retrieverで検証し、maskingの効果はinverted-U型で、retriever recallとmodel implicit filtering能力の相互作用に依存するとする。arXiv | 直接の実装コミュニティsignalより、論文自体が「一律適用は危険」という強いnegative signal。 | 上方修正：source-intake-only → use-now-narrow as eval warning | universal masking policyとして昇格不可。route/model/retrieverごとのregime依存が本質。 | research_xのlong search routeで、mask/offload/summary/full-historyを比較するfixtureを作る。勝つrouteだけ限定採用。 | rule/eval。plugin不要。 |
| RAG Knowledge Hub | source-intake-only | multi-source RAG例として有用か、実装候補か不透明だった | HF community article。Medium/arXiv/local PDFを取り込み、Qdrant、Gradio、NVIDIA Nemotron、Qwen2-VL、HF ZeroGPU、NVIDIA APIを使う構成。Hugging Face Medium抽出でFreedium mirrorを使うため、権利・規約リスクがある。Hugging Face | HF上のcommunity articleで、upvote/commentは小規模。production packageというよりhackathon/example。Hugging Face | 据え置き：source-intake-only | hosted API、Qdrant hosted secret、Freedium mirror、HF Spaces依存。source restorationとlegal/storage rightsが未解決。 | rights-cleared PDF/Web/arXivだけに限定し、local ingestion + citation-ready source bundleへ落とす最小実装を再設計。 | 何もしない。参考patternのみ。 |
| Visual Skills / AutoVisualSkill / VISUALSKILL | reference-only | text skillを超える価値はあるが、Codex基盤に入れる条件が曖昧だった | Visual Skill論文は、text-only skillの限界に対し、visual priors・binding・runtime constraintsを含むskillを提案。空間・UI・視覚確認が効く領域と、SQL/code synthesis等で不要な領域を分けている。arXiv VISUALSKILLはper-app multimodal skillとload_topic MCPを示す。arXiv | AutoVisualSkill GitHubはまだ小規模。mock smokeは可能だが、live generationはAPI/model環境依存。GitHub+1 | 据え置き：reference-only / future multimodal governance | screenshot保存、privacy、visual provenance、redaction、検証契約が未整備。research_xの主経路はテキストsource evidence。 | UI/browser/media workflowでtext-only skillが失敗する再現caseを作り、screenshot provenance・redaction・verificationを定義。 | 将来はSkill+MCP。今は rule：「空間情報が本質の時だけ」。 |
| WBS Viewer / progress visualization | future local hardening | 既存traceで足りるのか、local renderer候補か不透明だった | single-file-wbs はsingle HTML、local、zero dependency、JSON facts、planned/actual overlay、EVM-like progress axisを掲げる。GitHub Zenn記事はClaude CodeでのWBS更新効率化を説明。Zenn | GitHubは54 stars/27 issues程度。Chrome File System Access API依存、Firefox/Safari非対応、accessibility制約あり。GitHub | 据え置き：future local hardening | project evidenceではなく可視化UI。既存research-runs/show-run/workflow traceを置換する根拠がない。 | 具体的なobservability failureが発生し、必要fieldが既存traceにないこと。JSON schema + deterministic local rendererとして最小導入。 | rule/local renderer pattern。plugin不要。 |
| Ontology mention | not-actionable | 「オントロジーなんですね」だけでは元文脈が欠落 | X検索で確認できるのは短文断片のみ。X (formerly Twitter) 一般論としてGraphRAG/ontology-guided extractionはあるが、当該tweetの一次文脈には接続できない。 | 実装・コミュニティsignalなし。 | 据え置き：not-actionable | 原典・対象論文・対象ツールがない。GraphRAG一般論をこのtweetの根拠にしてはいけない。 | 元引用/リンク/対象論文が復元できること。さらにproject内でentity/relation ambiguityをontologyで解くevalが必要。 | 何もしない。 |
| Devin / Manus mention | not-actionable | 投稿は「Devin/Manusよりこっちかも」という感想で、対象が不明 | X断片は比較感想のみ。X (formerly Twitter) Devinは公式pricingでcloud agents、frontier model access、quota/extra usageを明記。devin.ai | Devinにはenterprise case studyやsecurity workflowsがあるが、これはhosted/proprietary provider評価であり、元投稿の「こっち」の根拠ではない。devin.ai | 据え置き：not-actionable / provider-gated if vendor eval | 元投稿から技術候補が特定できない。Devin/Manus自体はprovider・課金・データ境界の別審査。 | 具体機能、vendor eval目的、データ投入範囲、budget/quota、security reviewが明示されること。 | 何もしない。 |
| YAML-to-HTML / structure-view split | reference-only | reference-onlyだけでは薄く、local artifact patternとして昇格可能か不透明だった | GitHubはcore.yaml/view.yamlからHTML bundleを作るClaude Code plugin。server/API/build/CDN/networkなし、sandboxed iframe、HTML validationで外部script/fetch/storage等をブロック。GitHub Zenn記事は構造と表示の分離を説明。Zenn | Hatena bookmarkで一定の反応あり。GitHubは63 stars程度で初期。はてなブックマーク+1 | 上方修正：reference-only → rule / local artifact pattern candidate | third-party pluginを入れる必要はない。evidenceとpresentationを混ぜる危険がある。 | research_x reportで、evidence.yaml / view.yaml / validated HTML rendererを自前最小実装し、source citation分離を保てること。 | rule。将来はlocal Skill、pluginは不要。 |
| Archify | reference-only | diagram aidとしての価値はあるが、単に「図が綺麗」で止まっていた | GitHubはClaude/Codex/opencode用agent skill。plain-Englishからarchitecture/workflow/sequence/data-flow/lifecycle図をself-contained HTMLとして生成し、PNG/JPEG/WebP/SVG exportに対応。GitHub | 約1.2k stars。v2.5でtyped renderers/schema validation/CIを掲げるが、ajvなしではschema validationをskip。GitHub | 据え置き：reference-only / source-review before install | 図は証拠ではない。コード/IaC/traceとの整合validatorがない限り、見た目の良い誤図を作る危険がある。 | scoped diagram need、schema validation必須、code/trace/doc整合check、pinned zip/source review、no-network確認。 | Skill候補だが今は 何もしない。 |
| Ponytail | skill-source-review-required | 「過剰実装抑制」としてruleだけ採れば十分か、plugin価値があるか不明だった | GitHubは「best code is code you never wrote」系のYAGNI agent plugin。Codexではplugin marketplace追加後、hooksをreview/trustする導線。GitHub+1 | GitHub starsは非常に多い。実用関心は高いが、これは品質保証ではない。GitHub | 下方固定：rule only; no plugin | useful partは既に「stdlib/native/existing dependency確認」ruleで足りる。plugin/hook導入は過剰。YAGNIを過剰適用するとsecurity/a11y/future migrationを削る。 | repeated over-implementation regressionが出たら、local lint/eval ruleとして最小導入。pluginはsource reviewとhook audit後。 | rule。pluginは入れない。 |
| pdgkit | reference-only | deterministic DSL→render patternとして昇格余地があるか不透明だった | GitHubはPatentDSL.pdg からSVG/PNG/JPEG/PDF/PPTX等を生成するheadless library/CLI/MCP。local動作・ネットワーク通信なしを明記。GitHub MCPではpdg_validate/pdg_render/pdg_refsを提供。GitHub | 特許図面特化で、research_x一般図表とはfitが狭い。validate→diagnostics→修正ループは良いpattern。GitHub | 据え置き：reference-only / DSL-renderer pattern | patent/diagram output要件がない。Node/npm/MCP dependencyを増やす理由が不足。 | patent/technical drawing requirementが出た場合のみ、.pdg schema、validation、golden render test、license/font review。 | 何もしない。要件発生時はMCP/CLI候補。 |
| OCC-RAG | local-dependency | 有望だが、retrieverなのかanswerability checkerなのか誤解余地があった | 論文はOCC-RAGをcontext-grounded QA用SLMとし、explicit retrieval componentは内蔵しないと明記。3M超QA合成、faithfulness、calibrated abstention、structured citationsを狙う。arXiv GitHubはANSWERABLE/UNANSWERABLE status、contextからの回答/abstainを説明。GitHub+1 | README上はConFiQAやMuSiQue-Unで強いが、著者報告。repoはまだ小さい。GitHub | 据え置き：local-dependency | model download/runtime/calibrationが必要。retrieverではなくpost-retrieval reader/checkerなので、既存pipelineに雑に入れると責務が崩れる。 | answerable/unanswerable/conflicting-evidence fixtureで、既存insufficient-evidence behaviorを上回る。citation supportとabstention thresholdを校正。 | local model validator。Skillではない。 |
| Zvec | local-dependency | local vector backendとして有望だが、managed DB代替か不透明だった | GitHubはAlibabaのOSS in-process vector DB、v0.5.0、Apache-2.0、12k+ stars。GitHub+1 公式benchmarkはVectorDBBench、Cohere 1M/10M、QPS/Recall/load durationを測る。Zvec | HNでは226 points/45 comments。self-reported benchmarkの独立検証要求、local disk/page cache依存、object storage時のlatency悪化などが議論された。Hacker News | 据え置き：local-dependency | native dependency、cold/warm cache、disk性能、backup/restore、multi-process write、source-bundle restorationとの整合が未検証。managed vector DBの全面代替ではない。 | SQLite/FTS/current vector_projection/turbovec baselineと、同一corpusでlatency/recall/memory/cold start/update/deleteを比較。 | local dependency/backend。Skill/MCPではない。 |
| SkillAdaptor | codex-foundation-candidate | すでに強候補だが、コード導入/自動Skill更新まで進めるべきかが曖昧だった | 論文はfailed trajectoryからfirst actionable fault stepを特定し、責任skillにlinkし、explicit acceptance checksでtargeted updateするtraining-free framework。WebShop/PinchBench/Claw-Evalで評価。arXiv GitHubはOpenClaw live runsやWebShop/Claw-Eval optional環境を示す。GitHub | 関連してSkillRevise/SkillAxe/SkillCATなどskill self-evolution研究も出ており、分野の流れは強い。arXiv+2arXiv+2 | 据え置きだが最重要：codex-foundation-candidate | 外部runtime導入や自動Skill rewriteは危険。projectではhuman accept/reject、manifest validation、replayが先。 | ImprovementSignalに fault_step / responsible_artifact / candidate_diff / replay_result / qualifier_result / human_decision を入れ、local failed-run fixturesで検証。 | rule + Skill governance。plugin/MCPではない。 |

## 3. research_xで次に本当にsource intakeすべき上位5件

| rank | source intake target | reason |
| --- | --- | --- |
| 1 | SkillAdaptor | Codex基盤への写像が最も直接的。既存のImprovementSignal/Skill governanceに、失敗箇所特定・責任Skill帰属・replay qualifier・人間承認を追加する設計根拠になる。 |
| 2 | OCC-RAG | RAGの根本問題である「答える/答えない」をlocal answerability canaryとして評価できる。retrieverではなくpost-retrieval checkerとして明確化できた。 |
| 3 | Zvec | local vector/index backend候補として実装判断可能。ただし昇格条件はbenchmarkのみ。今source intakeして、dependency gateとbench designを固める価値がある。 |
| 4 | Hanno-Lab Bosun | 前回不透明だったHanno候補は、実際にはlocal relevance/judgment model候補だった。citation-support、dedup、memory graph edge判定に刺さる可能性がある。 |
| 5 | Agentmemory | installは不可だが、hooks/MCP/auto-capture/decay/search/injectの設計・失敗リスク・retention設計をレビューする価値が高い。既存memory基盤との比較対象として有用。 |

次点は **Stale observation masking**。これはsource intakeよりも、すぐに「masking/offload policyをroute別にevalする」チェック項目として扱う方が効率的です。

## 4. Codex基盤に入れるなら何が適切か

| candidate | appropriate surface |
| --- | --- |
| SkillAdaptor | rule + Skill governance。自動編集ではなく、proposal-only + replay qualifier + human accept。 |
| OCC-RAG | local model validator。Skillではない。answerability/abstention checker。 |
| Zvec | local dependency/backend。Skill/MCPではなくindex substrate。 |
| Bosun / Hanno relevance | rule/local classifier。citation support・dedup・edge warrant判定のeval候補。 |
| Agentmemory | 何もしない now。将来はMCP/pluginだが、hook/data-retention審査が先。 |
| Stale observation masking | rule/eval。一律masking禁止、route別eval必須。 |
| YAML-to-HTML | rule / local renderer pattern。third-party pluginではなく、自前schema+renderer。 |
| Visual Skills | 将来のSkill+MCP。今はprivacy/provenance未整備なのでrule止まり。 |
| Archify | 何もしない now。diagram scopeが出たらSkill候補。 |
| Ponytail | rule。plugin不要。 |
| pdgkit | 何もしない now。patent/diagram要件が出たらCLI/MCP候補。 |
| WBS Viewer | rule/local renderer pattern。observability failureが出るまで導入しない。 |
| JAMEL | 何もしない now。GUI exploration objectiveができたらeval source。 |
| RAG Knowledge Hub | 何もしない。権利・hosted API・example性が強い。 |
| Ontology mention | 何もしない。元文脈不足。 |
| Devin/Manus mention | 何もしない。provider/vendor evalとして別扱い。 |

## 最終判断

今回の追加調査で、曖昧だった保留理由は次のように整理できます。

- **昇格候補として本当に残る**: SkillAdaptor / OCC-RAG / Zvec / Bosun / Agentmemory。
- **ruleまたはevalとして吸収すべき**: Stale observation masking / YAML-to-HTML / Ponytail / WBS pattern。
- **将来の限定領域でのみ有効**: Visual Skills / Archify / pdgkit / JAMEL。
- **採用判断不能のまま**: Ontology mention / Devin-Manus mention。
- **昇格しない理由が透明になったもの**: RAG Knowledge Hubは、multi-source RAGの参考例ではあるが、Freedium・hosted Qdrant・NVIDIA API・HF Spaces依存のため、project-use候補ではなくsource-intake参考止まり。

現時点でコードや設定に触るなら、外部導入ではなく、**SkillAdaptor型のImprovementSignal schema追加、OCC-RAG型のanswerability fixture、Zvec benchmark stub、Bosun relevance fixture** のような評価・受け入れ条件側から入るのが妥当です。