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

目前版本：**v0.4.0 — Data, Statistics & Replication Pipeline**

## 核心能力

- 宣告式 `project.yaml` 與安全 AST 數值表達式；
- 有限宣告網格、邊界檢查與隨機反例搜索；
- CSV 欄位契約、缺失／無效值處理、來源雜湊與正規化快照；
- 對整份資料逐列執行經驗命題；
- 描述統計與 Student-$t$ 平均值信賴區間；
- 單樣本、獨立樣本、成對樣本與無母數檢定；
- Pearson／Spearman 相關分析；
- 固定種子的百分位 Bootstrap 信賴區間；
- 敏感度、殘差、參數掃描與雙目標 Pareto 前沿；
- 重複實驗、種子展開與多程序並行批次；
- CSV、JSON、Markdown、PNG／SVG／PDF 證據包。

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
felra batch examples/repeated_batch/batch.yaml --output artifacts/repeated --workers 2
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

- `docs/PROJECT_SPEC_v0.4.md`
- `docs/DATA_STATISTICS_PIPELINE_v0.4.md`
- `docs/BATCH_REPLICATION_v0.4.md`
- `schema/project-v0.4.schema.json`
- `schema/batch-v0.4.schema.json`

完整理論設計見 `docs/GCPR-RWL-FELRA_技術白皮書_v1.0.md`。
