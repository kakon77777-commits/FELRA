# FELRA Repeated & Parallel Batch v0.4

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

上述規格展開為：

```text
trial_replicates__r001
trial_replicates__r002
trial_replicates__r003
```

`workers` 使用獨立 Python 程序並行執行，每個實驗擁有獨立輸出目錄。批次證據新增：

- `batch_summary.csv`：逐次執行結果；
- `replicate_summary.csv`：群組成功率、通過率與平均耗時；
- `batch_manifest.json`：完整展開後的機器可讀紀錄。

並行只改變排程，不應改變由明確種子控制的結果。
