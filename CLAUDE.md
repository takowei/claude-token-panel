# claude-token-panel

本地網頁儀表板，顯示每次 Claude Code 任務的 token 消耗，標示是否在合理範圍內。在 Windows 瀏覽器 `localhost:8765` 開啟即可查看。

## 狀態（2026-06-07）

✅ 可用。FastAPI 後端讀取 `~/.claude/projects/` 的 JSONL 歷史，前端每 10 秒自動刷新。

## 技術棧

- **後端**：Python FastAPI（`main.py`，port 8765）
- **前端**：單頁 `index.html` + vanilla JS，自動刷新
- **資料來源**：`~/.claude/projects/**/*.jsonl`（每個 project 的對話歷史）

## 關鍵檔案

```
main.py      ← FastAPI 後端：讀 JSONL → 計算 token 統計 → API
index.html   ← 前端：token 列表 + 顏色分類
start.sh     ← 一鍵啟動（bootstrap pip + 啟動 uvicorn）
launch.bat   ← Windows 雙擊啟動（呼叫 start.sh）
widget.ps1   ← PowerShell 啟動版本
```

## 快速啟動

```bash
bash start.sh
# 瀏覽器開啟 http://localhost:8765
```

Windows：直接雙擊 `launch.bat`。

`start.sh` 會自動 bootstrap pip（無需系統 pip）：

```bash
PYLIB=$(python3 -c "import tempfile,os; print(os.path.join(tempfile.gettempdir(),'pylib'))")
python3 /usr/share/python-wheels/pip-22.0.2-py3-none-any.whl/pip install fastapi uvicorn --target "$PYLIB" -q
PYTHONPATH="$PYLIB" python3 main.py
```

## Token 閾值

| 顏色  | 範圍      | 說明         |
| ----- | --------- | ------------ |
| 🟢 綠 | < 10k     | 簡單任務     |
| 🟡 黃 | 10k – 50k | 中等任務     |
| 🔴 紅 | > 50k     | 確認是否必要 |

週用量上限參考值：`WEEK_LIMIT = 26,052,993`（錨定在建立時的週總量）。

## API 端點

```
GET /api/sessions        ← 所有 session 的 token 統計
GET /api/week-summary    ← 本週總用量 + 百分比
GET /                    ← 前端頁面
```
