# Claude stream samples

**Synthetic，尚未與真實輸出比對。**

這些 `.jsonl` 檔是依 `claude --help` 與公開文件記載的
`claude -p --output-format stream-json --verbose` 事件形狀手工構造的，不是
錄製檔，產生時沒有呼叫任何模型。內容全部是佔位字串，不含真實 prompt、
fixture、session 或憑證。

| 檔案 | 內容 |
|---|---|
| `dispatch-ok.jsonl` | parent 呼叫一次 `Agent`（`subagent_type: plan-verifier`），child 回 `READY` |
| `no-agent-call.jsonl` | parent 自己回答，沒有 `Agent` 呼叫 |
| `unknown-event.jsonl` | 在 `dispatch-ok` 中插入一個解析器不認得的事件 |

claude-eval-parity AC-CE-018 的最小 live 呼叫完成後，要用真實輸出核對或
取代這些樣本；在那之前，`install/role_fitness_claude.py` 的解析器遇到不認得
的形狀一律 fail closed。
