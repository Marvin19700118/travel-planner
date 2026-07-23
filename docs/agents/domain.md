# Domain Docs

Engineering skills 探索 codebase 時，應如何消費這個 repo 的 domain documentation。

## Before exploring, read these

- repo 根目錄的 **`CONTEXT.md`**，或
- repo 根目錄的 **`CONTEXT-MAP.md`**（如果存在）— 它指向每個 context 的一個 `CONTEXT.md`。讀取與當前話題相關的每個文件。
- **`docs/adr/`** — 讀取與你即將處理區域相關的 ADRs。在 multi-context repos 中，也檢查 `src/<context>/docs/adr/` 中的 context-scoped decisions。

如果這些文件不存在，**靜默繼續**。不要標記缺失；不要提前建議創建。producer skill（`/grill-with-docs`）會在 terms 或 decisions 實際被解決時懶創建它們。

## File structure

Single-context repo（大多數 repos）：

```
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-event-sourced-orders.md
│   └── 0002-postgres-for-write-model.md
└── src/
```

Multi-context repo（根目錄存在 `CONTEXT-MAP.md`）：

```
/
├── CONTEXT-MAP.md
├── docs/adr/                          ← system-wide decisions
└── src/
    ├── ordering/
    │   ├── CONTEXT.md
    │   └── docs/adr/                  ← context-specific decisions
    └── billing/
        ├── CONTEXT.md
        └── docs/adr/
```

## Use the glossary's vocabulary

當你的輸出命名某個 domain concept 時（issue title、refactor proposal、hypothesis、test name），使用 `CONTEXT.md` 中定義的 term。不要漂移到 glossary 明確避免的 synonyms。

如果你需要的概念還不在 glossary 中，這是一個信號：要麼你正在發明項目沒有使用的語言（重新考慮），要麼確實存在缺口（為 `/grill-with-docs` 記錄）。

## Flag ADR conflicts

如果你的輸出與現有 ADR 矛盾，明確指出，而不是靜默覆蓋：

> _Contradicts ADR-0007 (event-sourced orders) — but worth reopening because…_
