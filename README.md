# FELRA

**FELRA — Formal Evolving Logic-Rule Architecture**  
**形式演化邏輯—規則架構**

FELRA 是 GCPR–RWL–FELRA 的 Python 優先學術驗證與視覺化工作台。它先把理論與資料轉換成可重現計算證據，再將穩定結果提升為形式規約與證明義務。

$$
\text{理論／資料}
\rightarrow
\text{Python 驗證與統計分析}
\rightarrow
\text{反例、殘差、敏感度與圖形}
\rightarrow
\text{修正命題}
\rightarrow
\text{FELRA 規約}
\rightarrow
\text{SMT／Lean／RWL}.
$$

目前版本：**v0.7.0 — Preregistration, Provenance, Replay & Paper Export**

## 核心能力

- 宣告式 `project.yaml` 與安全 AST 數值表達式；
- 有限宣告網格、邊界檢查與隨機反例搜索；
- CSV／JSON／JSONL 欄位契約、缺失／無效值處理、來源雜湊與正規化快照；
- 對整份資料逐列執行經驗命題；
- 描述統計與 Student-$t$ 平均值信賴區間；
- 單樣本、獨立樣本、成對樣本與無母數檢定；
- Pearson／Spearman 相關分析；
- 固定種子的百分位 Bootstrap 信賴區間；
- 單樣本、成對、獨立樣本與相關分析的統計功效曲線；
- Bootstrap／子樣本重抽樣穩健性、符號穩定度與分布證據；
- 依專案、分析、資料雜湊與種子建立的內容定址分析快取；
- Bonferroni、Holm 與 Benjamini–Hochberg 多重比較校正；
- 具名稱的 Cohen/Hedges、rank-biserial 與相關效應量；
- 數值迴歸交叉驗證、out-of-fold 預測與共享折次模型比較；
- 附加式 JSONL 研究實驗註冊表與 `felra registry` 查詢；
- 敏感度、殘差、參數掃描與雙目標 Pareto 前沿；
- 重複實驗、種子展開與多程序並行批次；
- CSV、JSON、Markdown、PNG／SVG／PDF 證據包。
- 科學計畫預註冊與 `warn`／`strict` 執行鎖定；
- Claim、資料、分析、圖形與報告的 JSON／DOT／SVG 證據溯源圖；
- 科學結果 SHA-256 指紋與 `felra replay` 獨立重播；
- `felra export` 論文級 Methods、Results、Limitations、CITATION 與檔案雜湊包；

## 安裝

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

pip install -e ".[dev]"
```

## 快速開始

```bash
felra init my-theory
felra run my-theory/project.yaml --output my-theory/artifacts/run
```

執行不同類型的示範：

```bash
felra run examples/basic/project.yaml --output artifacts/basic
felra run examples/advanced/project.yaml --output artifacts/advanced
felra run examples/data/project.yaml --output artifacts/data
felra run examples/robustness/project.yaml --output artifacts/robustness
felra run examples/research_registry/project.yaml --output artifacts/research-registry
felra registry examples/research_registry/.felra-registry/research_runs.jsonl --limit 10
felra batch examples/repeated_batch/batch.yaml --output artifacts/repeated --workers 2
felra preregister examples/reproducibility/project.yaml --output examples/reproducibility/preregistration.json
felra run examples/reproducibility/project.yaml --output artifacts/reproducibility
felra replay artifacts/reproducibility --output artifacts/replay
felra export artifacts/reproducibility --output artifacts/paper-bundle
```

## 外部資料規格

```yaml
datasets:
  trial:
    path: data/clinical_trial.csv
    format: csv
    on_error: drop
    columns:
      subject_id: str
      group: str
      age: int
      score: float
      note: {type: str, required: false}
```

每個資料集會產生：

```text
datasets/trial/
├── dataset_report.md
├── normalized.csv
└── quality.json
```

來源檔不會被覆寫；`normalized.csv` 是依欄位契約產生的可重現投影。

## 資料命題

```yaml
claims:
  - id: adult_finite_scores
    statement: 所有納入資料皆為成年且分數有限
    dataset: trial
    expression: age >= 18 and isfinite(score)
    required_checks: [dataset_rows]
```

`dataset_rows` 遍歷正規化後的全部資料列。結果只對該資料集成立，不自動外推到母體。

## 統計分析

### 描述統計

```yaml
analyses:
  - id: grouped_descriptives
    type: descriptive
    dataset: trial
    columns: [before, after, score]
    group_by: group
    confidence: 0.95
```

平均值信賴區間：

$$
\bar{x}\pm t_{1-\alpha/2,n-1}\frac{s}{\sqrt n}.
$$

### 假設檢定

```yaml
  - id: treatment_score_test
    type: hypothesis_test
    dataset: trial
    test: independent_t
    column: score
    group_by: group
    groups: [control, treatment]
    equal_var: false
    alternative: two-sided
    alpha: 0.05
```

支援：`one_sample_t`、`independent_t`、`paired_t`、`mann_whitney`、`wilcoxon`、`pearson`、`spearman`。

### Bootstrap 信賴區間

```yaml
  - id: score_bootstrap_ci
    type: bootstrap_ci
    dataset: trial
    column: score
    statistic: mean
    confidence: 0.95
    resamples: 5000
```

FELRA 保存重抽樣分布、種子、估計量、標準誤與百分位數上下界。


## 功效、穩健性與快取

```yaml
execution:
  cache: true
  cache_dir: .felra-cache

analyses:
  - id: power_plan
    type: power
    test: independent_t
    effect_size: 0.6
    alpha: 0.05
    target_power: 0.8

  - id: robust_effect
    type: robustness
    dataset: trial
    statistic: mean_difference
    columns: [score]
    group_by: group
    groups: [control, treatment]
    method: bootstrap
    repetitions: 2000
```

第二次執行完全相同的分析時，`metrics.json` 會記錄 `cache_hit: true`。任何專案內容、資料來源雜湊、分析規格、FELRA 版本或執行種子的變化都會產生不同指紋。

## 多重比較、交叉驗證與模型註冊

```yaml
registry:
  enabled: true
  path: .felra-registry/research_runs.jsonl
  tags: [paper-01, synthetic]

analyses:
  - id: corrected_groups
    type: multiple_comparisons
    dataset: study
    column: score
    group_by: group
    groups: [baseline, method_a, method_b]
    correction: holm

  - id: compare_models
    type: model_comparison
    dataset: study
    target: y
    features: [x, z]
    folds: 5
    primary_metric: rmse
    models:
      - {name: linear, type: linear}
      - {name: quadratic, type: polynomial, degree: 2}
```

所有候選模型使用相同折次與種子。模型排名屬探索性選擇；確認性性能估計仍應使用巢狀交叉驗證或獨立測試集。

## 預註冊、溯源與重播

```yaml
preregistration:
  enabled: true
  path: preregistration.json
  mode: strict
```

先建立不可覆寫的研究計畫紀錄：

```bash
felra preregister project.yaml --output preregistration.json
felra verify-preregistration project.yaml --record preregistration.json
```

`strict` 模式下，只要參數域、命題、分析、資料宣告或種子等科學計畫發生改變，執行就會停止；`warn` 模式則保留偏離紀錄並繼續。快取路徑、Registry 路徑等純操作設定不納入計畫指紋。

每次執行都會輸出：

```text
provenance/provenance.json
provenance/provenance.dot
provenance/provenance.svg
replay_project.yaml
manifest.json  # 包含 result_sha256
```

重播與論文匯出：

```bash
felra replay artifacts/run --output artifacts/replay
felra export artifacts/run --output artifacts/paper-bundle
```

重播成功只表示在目前軟體與浮點環境中取得同一科學結果指紋，不等同於跨平台位元級一致，也不證明研究設計正確。

## 重複與並行批次

```yaml
batch:
  id: repeated_statistics
  workers: 2

experiments:
  - id: trial_replicates
    project: ../data/project.yaml
    repeat:
      count: 3
      seed_path: execution.seed
      seed_start: 101
      seed_step: 101
```

也可由命令列覆寫工作程序數：

```bash
felra batch batch.yaml --output artifacts/batch --workers 4
```

批次輸出 `batch_summary.csv` 與 `replicate_summary.csv`，分別保存逐次實驗與重複群組的成功率、通過率及耗時。

## 參數空間分析

v0.1–v0.3 的能力保持相容：

- `sensitivity`：有限差分局部敏感度；
- `residual`：MAE、RMSE、偏差與殘差圖；
- `parameter_sweep`：一至高維目標地景；
- `pareto`：有限候選集上的精確雙目標非支配前沿。

## 證據包

```text
artifacts/data/
├── datasets/
├── claims/
├── analyses/
├── figures/
├── manifest.json
├── project_report.md
└── project_snapshot.yaml
```

所有結果都記錄專案 SHA-256、資料來源 SHA-256、隨機種子、Python／NumPy／SciPy 版本與輸出路徑。

## 驗證與統計邊界

FELRA 的 Python 結果是有限資料、有限精度、有限預算與特定統計假設下的計算證據，不等同於一般數學證明。$p$ 值不是假設為真的機率；拒絕虛無假設不自動建立因果關係；未拒絕虛無假設也不代表兩者等價。

## 開發檢查

```bash
pytest
ruff check src tests
python -m compileall -q src tests
```

規格文件：

- `docs/PROJECT_SPEC_v0.6.md`
- `docs/MODEL_SELECTION_REGISTRY_v0.6.md`
- `docs/POWER_ROBUSTNESS_CACHE_v0.5.md`
- `docs/DATA_STATISTICS_PIPELINE_v0.4.md`
- `docs/BATCH_REPLICATION_v0.4.md`
- `schema/project-v0.6.schema.json`
- `schema/batch-v0.5.schema.json`

完整理論設計見 `docs/GCPR-RWL-FELRA_Technical_Whitepaper_zh-TW_v1.0.md`。
