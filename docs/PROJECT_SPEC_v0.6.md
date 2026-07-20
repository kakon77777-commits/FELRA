# FELRA Project Specification v0.6

v0.6 在 v0.5 規格上增加三種分析與一個專案級註冊區塊。

## `multiple_comparisons`

```yaml
- id: corrected_groups
  type: multiple_comparisons
  dataset: study
  column: score
  group_by: group
  groups: [control, method_a, method_b]
  test: independent_t
  correction: holm
  alpha: 0.05
```

`comparisons` 可明確給定成對組合；省略時會對 `groups` 或資料集中全部群組建立所有兩兩比較。

## `cross_validation`

```yaml
- id: cv_model
  type: cross_validation
  dataset: study
  target: y
  features: [x, z]
  model: polynomial
  degree: 2
  folds: 5
  shuffle: true
  seed: 606
  standardize: true
```

## `model_comparison`

```yaml
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

## `registry`

```yaml
registry:
  enabled: true
  path: .felra-registry/research_runs.jsonl
  tags: [v0.6, paper]
  notes: 可選備註。
```

完整機器可讀規格見 `schema/project-v0.6.schema.json`。
