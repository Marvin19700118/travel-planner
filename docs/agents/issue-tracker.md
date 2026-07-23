# Issue tracker: GitHub

這個 repo 的 issues 和 PRDs 存放在 GitHub issues 中。所有操作都使用 `gh` CLI。

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`。多行 body 使用 heredoc。
- **Read an issue**: `gh issue view <number> --comments`，用 `jq` 過濾 comments，並同時獲取 labels。
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'`，按需加上 `--label` 和 `--state` filters。
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

從 `git remote -v` 推斷 repo；在 clone 內運行時，`gh` 會自動處理。

## When a skill says "publish to the issue tracker"

創建一個 GitHub issue。

## When a skill says "fetch the relevant ticket"

運行 `gh issue view <number> --comments`。
