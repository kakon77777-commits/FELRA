# FELRA `project.yaml` 規格 v0.2

FELRA 將研究命題表達為可執行但受限的 YAML 規格。其基本映射為：

$$
\mathcal P
=
(\Theta,\mathcal C,\mathcal V,\mathcal F,\mathcal E)
$$

其中：

- $\Theta$：參數與聲明域；
- $\mathcal C$：可計算命題；
- $\mathcal V$：驗證通道；
- $\mathcal F$：圖形規格；
- $\mathcal E$：執行預算與隨機種子。

## 最小範例

```yaml
project:
  id: nonnegative_square
  title: 平方函數非負性
  language: zh-TW

execution:
  max_evaluations: 200000
  random_samples: 20000
  seed: 42

parameters:
  x:
    type: float
    range: [-10, 10]
    samples: 10001

claims:
  - id: claim_001
    statement: 在聲明域內，x² 非負
    expression: x ** 2 >= 0
    required_checks: [numerical, boundaries, counterexample_search]

outputs:
  figures:
    - id: square_curve
      type: line
      x: x
      y: x ** 2
      title: 平方函數
      filename: square_curve.png
```

## 參數

連續參數：

```yaml
x:
  type: float
  range: [-1.0, 1.0]
  samples: 1001
```

整數參數：

```yaml
n:
  type: int
  range: [1, 100]
  samples: 100
```

顯式離散值：

```yaml
k:
  type: int
  values: [2, 3, 5, 7, 11]
```

對 $d$ 個參數，完整宣告網格大小為：

$$
N_{\mathrm{grid}}=\prod_{i=1}^{d}N_i.
$$

若

$$
N_{\mathrm{grid}}\leq N_{\max},
$$

FELRA 會遍歷完整笛卡兒積；否則切換為有固定種子的預算式均勻取樣，並在報告中將 `exhaustive_declared_grid` 標記為 `false`。

## 命題表達式

允許：

- 算術：`+ - * / // % **`
- 比較：`== != < <= > >=`
- 布林：`and or not`，以及 `& | ~`
- 條件式：`a if condition else b`
- 常數：`pi e inf`
- 函數：`abs sqrt exp log log10 sin cos tan arcsin arccos arctan minimum maximum clip where isfinite isnan`

範例：

```yaml
expression: x ** 2 + y ** 2 >= 0
expression: isfinite(log(x)) and x > 0
expression: where(x >= 0, x, -x) == abs(x)
```

不允許屬性存取、匯入、索引任意物件、lambda、理解式或一般 Python 函數呼叫。FELRA 使用 AST 解譯器，不使用 `eval`。

## 驗證通道

### `numerical`

在完整宣告網格或預算式樣本上檢查命題。

### `boundaries`

對每個參數取最小值與最大值，檢查至多 $2^d$ 個角點。

### `counterexample_search`

使用獨立隨機種子，在參數域中搜索反例。此通道是啟發式搜索，不構成無反例證明。

## 圖形

| `type` | 必要欄位 | 用途 |
|---|---|---|
| `line` | `x`, `y` | 一維函數曲線 |
| `scatter` | `x`, `y` | 散點關係 |
| `histogram` | `x` 或 `y` | 數值分布 |
| `heatmap` | `x`, `y`, `z` | 二維參數地景 |
| `contour` | `x`, `y`, `z` | 等高線／等值面投影 |
| `phase_map` | `x`, `y`, `z` | 布林或離散相位區域 |

`line` 與 `scatter` 的 `x` 在 v0.2 必須是參數名稱；其他未變動參數固定在各自宣告軸的中點。

## 證據輸出

每次執行都保存：

- 原始設定快照；
- 設定 SHA-256；
- Python、平台與 NumPy 版本；
- 各通道樣本數與取樣策略；
- 反例的實際輸入；
- 圖形路徑；
- Markdown 與 JSON 報告。

FELRA v0.2 的「全域驗證」精確指：

> 在明確的有限聲明網格內完成全遍歷，或在超出預算時明確降級為可重現的有限樣本驗證。

它不表示已證明無限連續域上的普遍命題。
