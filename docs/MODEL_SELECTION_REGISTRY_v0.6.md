# FELRA v0.6：多重比較、模型驗證與研究實驗註冊

## 1. 版本定位

FELRA v0.6 將資料分析管線從單一檢定與單一模型，推進到「比較族—預測驗證—模型選擇—實驗登錄」的完整研究流程：

$$
\mathcal E_{0.6}
=
\mathcal E_{0.5}
\oplus
\mathcal M_c
\oplus
\mathcal E_s
\oplus
\mathcal C_v
\oplus
\mathcal M_s
\oplus
\mathcal R_e.
$$

其中：

- $\mathcal M_c$：多重比較校正；
- $\mathcal E_s$：標準化效應量；
- $\mathcal C_v$：交叉驗證；
- $\mathcal M_s$：共享折次模型比較；
- $\mathcal R_e$：附加式研究實驗註冊表。

## 2. 多重比較

支援同一比較族中的：

- `none`；
- `bonferroni`；
- `holm`；
- `fdr_bh`。

每個分析區塊定義一個比較族。校正後 $p$ 值只對該族有效；增加或移除比較會改變校正結果。

## 3. 標準化效應量

假設檢定現在同時保存：

- 單樣本 Cohen's $d$ 與 Hedges' $g$；
- 獨立樣本 Cohen's $d$、Hedges' $g$ 與 Glass's $\Delta$；
- 成對樣本 $d_z$ 與小樣本校正後 $g_z$；
- Mann–Whitney rank-biserial correlation；
- Wilcoxon matched rank-biserial correlation；
- Pearson $r$ 與 Spearman $\rho$。

顯著性與效應量必須分開解讀。小 $p$ 值不等於大效應，大效應也不自動代表因果關係。

## 4. 交叉驗證

`cross_validation` 支援數值型特徵上的線性與多項式最小平方法模型。資料先移除不完整列，再於每個訓練折內估計標準化參數，避免把測試折資訊洩漏到訓練流程。

目前輸出：

- 每折 RMSE、MAE、$R^2$；
- 全部 out-of-fold 預測；
- 殘差；
- 平均與折間標準差；
- 觀測值—預測值圖；
- 殘差分布圖。

多項式基底目前包含每一特徵的逐次冪，不包含交互項。

## 5. 模型比較

`model_comparison` 讓所有候選模型使用完全相同的折次與隨機種子，以降低由資料切分差異造成的比較噪音。

支援以 RMSE、MAE 或 $R^2$ 排名。此排名屬探索性模型選擇；若要對最終模型性能作確認性估計，應使用外部測試集或巢狀交叉驗證。

## 6. 實驗註冊表

啟用方式：

```yaml
registry:
  enabled: true
  path: .felra-registry/research_runs.jsonl
  tags: [paper-01, synthetic]
  notes: 此資料為合成示範。
```

每次執行會附加一筆 JSONL 紀錄，包含：

- Run ID；
- FELRA 版本；
- 專案與設定雜湊；
- 執行時間；
- 通過狀態；
- 資料來源雜湊；
- 分析清單；
- 快取命中狀態；
- 標籤、備註與警告。

同時在本次 Evidence Bundle 中寫入 `registry_record.json`。

查詢：

```bash
felra registry .felra-registry/research_runs.jsonl --limit 20
felra registry .felra-registry/research_runs.jsonl --project paper-01 --status passed
```

註冊表是附加式研究索引，不是防竄改帳本，也不取代 Git、資料版本控制或正式預註冊平台。
