# FELRA Project Specification v0.4

FELRA v0.4 同時支援「參數空間研究」與「外部資料研究」。專案至少需要一個 `claim` 或 `analysis`。

## 外部 CSV 資料

```yaml
datasets:
  trial:
    path: data/clinical_trial.csv
    format: csv
    on_error: drop
    missing_values: ["", NA, N/A, null]
    columns:
      group: str
      age: int
      score: float
      note: {type: str, required: false}
```

`on_error` 有三種策略：

- `drop`：丟棄缺失或無法轉型的必要欄位資料列；
- `error`：遇到第一個問題立即停止；
- `keep`：以 `NaN`／空值保留，交由後續分析處理。

每個資料集會輸出來源 SHA-256、缺失／無效計數、重複列數、正規化 CSV 與資料品質報告。

## 資料列命題

```yaml
claims:
  - id: adult_finite_scores
    statement: 所有納入資料皆為成年且分數有限
    dataset: trial
    expression: age >= 18 and isfinite(score)
    required_checks: [dataset_rows]
```

此檢查遍歷正規化後的全部資料列。它證明的是資料集內命題，不是母體上的普遍定理。

## 描述統計與平均值信賴區間

```yaml
analyses:
  - id: grouped_descriptives
    type: descriptive
    dataset: trial
    columns: [before, after, score]
    group_by: group
    confidence: 0.95
```

平均值的 Student-$t$ 信賴區間為：

$$
\bar{x}\pm t_{1-\alpha/2,n-1}\frac{s}{\sqrt n}.
$$

## 假設檢定

`hypothesis_test` 支援：

- `one_sample_t`；
- `independent_t`（Welch 或等變異）；
- `paired_t`；
- `mann_whitney`；
- `wilcoxon`；
- `pearson`；
- `spearman`。

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

FELRA 報告統計量、$p$ 值、樣本數、決策與可計算的效應量。`reject_null` 不等於理論已被證實；`fail_to_reject_null` 也不等於虛無假設為真。

## Bootstrap 信賴區間

```yaml
  - id: score_bootstrap_ci
    type: bootstrap_ci
    dataset: trial
    column: score
    statistic: mean
    confidence: 0.95
    resamples: 5000
```

v0.4 使用固定種子的百分位數 Bootstrap，輸出完整重抽樣分布、標準誤與上下界。

完整 JSON Schema：`schema/project-v0.4.schema.json`。
