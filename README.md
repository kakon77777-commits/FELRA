# FELRA

**FELRA — Formal Evolving Logic-Rule Architecture**  
**形式演化邏輯—規則架構**

FELRA 是 GCPR–RWL–FELRA 架構的 Python 優先學術驗證工作台。首階段聚焦於：

- 將論文命題轉換為可執行研究專案；
- 進行數值、邊界、性質、敏感度與反例搜索；
- 大量生成可追溯的學術圖形；
- 輸出 Markdown 驗證報告與機器可讀證據；
- 將穩定結果逐步提升為 FELRA 條款與更嚴格的形式證明義務。

## 研究流程

$$
\text{構想}
\rightarrow
\text{Python 初步驗證}
\rightarrow
\text{反例與圖形探索}
\rightarrow
\text{修正命題}
\rightarrow
\text{FELRA 規約}
\rightarrow
\text{SMT／Lean／RWL}
$$

## 快速開始

```bash
python -m venv .venv
# Windows
.venv\\Scripts\\activate
# Linux / macOS
source .venv/bin/activate

pip install -e ".[dev]"
felra demo --output artifacts/demo
pytest
```

執行後將產生：

```text
artifacts/demo/
├── figures/
│   └── nonnegative_square.png
├── metrics.json
└── validation_report.md
```

## 建立研究專案

```bash
felra init my-theory
```

產生的 `project.yaml` 可描述命題、參數域、所需檢查與輸出圖形。

## 專案結構

```text
src/felra/
├── cli.py                 # CLI
├── models.py              # 研究命題與證據資料模型
├── evidence.py            # 報告與證據輸出
├── validation/            # Python 驗證編排
└── figures/               # 圖形工廠
```

## 狀態

目前為 **MVP / research preview**。Python 計算結果屬於有限域、有限精度與有限預算內的機器驗證，不等同於一般數學證明。

完整技術設計見 [`docs/GCPR-RWL-FELRA_技術白皮書_v1.0.md`](docs/GCPR-RWL-FELRA_技術白皮書_v1.0.md)。
