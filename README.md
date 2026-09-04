# Claude Token Panel — 本地用量儀表板

本地網頁儀表板：解析 Claude Code 的對話歷史（`~/.claude/projects/**/*.jsonl`），視覺化每次任務的 token 消耗與本週用量，顏色標示是否在合理範圍。

## 功能

- **後端**（FastAPI）：掃描所有 project 的 JSONL → 聚合每個 session 的 input/cache/output token → REST API。
- **前端**（單頁 vanilla JS）：每 10 秒自動刷新的 session 列表，依用量綠/黃/紅分類，含本週總量與百分比。
- **用量護欄**（`usage_guard.py`）：滾動視窗（預設 5h）用量估計，供自動化流程在接近上限時自我節流（避免長任務跑到一半被切斷）。

## 技術棧

Python（FastAPI / uvicorn）、HTML + vanilla JS。資料來源：本地 JSONL（唯讀）。

## 快速開始

```bash
bash start.sh                       # 自動 bootstrap pip + 啟動，→ http://localhost:8765
python3 usage_guard.py --print      # 印出當前滾動視窗用量（JSON）
```

## 架構

```
main.py          FastAPI：讀 JSONL → token 統計 → /api/sessions
index.html       前端：列表 + 顏色分類 + 自動刷新
usage_guard.py   滾動視窗用量估計 + 門檻警示（可作 hook 或自我節流）
start.sh         一鍵啟動（含 pip bootstrap）
```

## 顏色閾值

🟢 <10k（簡單任務）｜🟡 10k–50k（中等）｜🔴 >50k（確認是否必要）。
