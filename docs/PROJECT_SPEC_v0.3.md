# FELRA Project Specification v0.3

## 1. 根結構

```yaml
project: {}
execution: {}
parameters: {}
claims: []
analyses: []
outputs:
  figures: []
```

`analyses` 在 v0.3 中是可選欄位；v0.2 專案可直接執行。

## 2. `project`

```yaml
project:
  id: unique_project_id
  title: 顯示標題
  language: zh-TW
```

## 3. `execution`

```yaml
execution:
  max_evaluations: 200000
  random_samples: 20000
  seed: 42
```

- `max_evaluations`：完整宣告網格超出此值時，改用預算式均勻抽樣。
- `random_samples`：反例搜索樣本數。
- `seed`：專案基準種子；反例搜索使用 `seed + 1`。

## 4. `parameters`

連續參數：

```yaml
x:
  type: float
  range: [-10, 10]
  samples: 1001
```

整數參數：

```yaml
n:
  type: int
  range: [1, 100]
  samples: 100
```

離散值：

```yaml
order:
  type: int
  values: [2, 4, 6, 8]
```

## 5. `claims`

```yaml
claims:
  - id: claim_001
    statement: 在聲明域內，x² 非負
    expression: x ** 2 >= 0
    status: hypothesis
    required_checks:
      - numerical
      - boundaries
      - counterexample_search
    max_counterexamples: 20
```

支援驗證通道：

- `numerical`
- `boundaries`
- `counterexample_search`

## 6. 安全表達式

允許：

- 算術：`+ - * / // % **`
- 比較：`== != < <= > >=`
- 布林：`and or not`、`& | ~`
- 條件式：`a if condition else b`
- 常數：`pi e inf`
- 函數：`abs sqrt exp log log10 sin cos tan arcsin arccos arctan minimum maximum clip where isfinite isnan`

禁止：

- 屬性存取；
- 匯入；
- Lambda；
- 任意函數呼叫；
- 列表／集合／字典理解式；
- 檔案、網路與程序存取。

## 7. `analyses`

### 7.1 `sensitivity`

```yaml
- id: local_sensitivity
  type: sensitivity
  title: 局部敏感度
  expression: a * x ** 2 + b
  parameters: [x, a, b]
  baseline: {x: 1.0, a: 1.0, b: 1.0}
  relative_step: 0.001
  # absolute_step: 0.01
  claim_id: claim_001
```

- `parameters` 省略時分析全部參數。
- `baseline` 省略的參數使用宣告軸中央值。
- `absolute_step` 若存在，優先於 `relative_step`。
- 整數參數的差分步長至少為 $1$。
- 離散參數使用基準值兩側最近的宣告值。

### 7.2 `residual`

```yaml
- id: approximation_residual
  type: residual
  title: 近似殘差
  reference: exp(x)
  approximation: 1 + x + x ** 2 / 2
  independent: x
  tolerance: 0.5
  bins: 40
```

殘差定義：

$$
r = \text{reference}-\text{approximation}
$$

`tolerance` 以 RMSE 判定分析是否成功；省略時僅要求存在有限樣本。

### 7.3 `parameter_sweep`

```yaml
- id: landscape
  type: parameter_sweep
  title: 參數地景
  objective: (a - 1.2) ** 2 + (b - 0.7) ** 2
  parameters: [a, b]
  fixed: {x: 1.0}
  goal: minimize
  top_k: 20
```

- `goal`：`minimize` 或 `maximize`。
- `parameters` 省略時掃描全部參數。
- `fixed` 用於指定未掃描參數；其餘未掃描參數採中央值。
- 一維完整網格輸出曲線；二維完整網格輸出熱圖與等高線；其他情況輸出分布圖。

### 7.4 `pareto`

```yaml
- id: tradeoff
  type: pareto
  title: 雙目標取捨
  parameters: [a, b]
  fixed: {x: 1.0}
  objectives:
    - name: error
      expression: (a - 1.2) ** 2 + (b - 0.7) ** 2
      goal: minimize
    - name: complexity
      expression: a + b
      goal: minimize
```

v0.3 僅接受兩個目標，並在有限候選集上精確計算非支配點。

## 8. `outputs.figures`

支援：

- `line`
- `scatter`
- `histogram`
- `heatmap`
- `contour`
- `phase_map`

分析通道本身會另外自動生成敏感度、殘差、地景與 Pareto 圖。

## 9. 輸出與可重現性

每次執行保存：

- 專案 YAML 快照；
- 設定 SHA-256；
- Python、平台、NumPy 版本；
- 取樣策略；
- 是否完整遍歷宣告網格；
- 隨機種子；
- CSV、JSON、Markdown 與圖形。
