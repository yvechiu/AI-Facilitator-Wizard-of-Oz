# AI Facilitator Wizard of Oz 本地端控制台

以 Python 3.12、Streamlit、Discord REST API、SQLite 建立的繁體中文研究控制台。預設 Demo，僅監聽 `127.0.0.1`，無 LLM、無付費服務，也不會持續讀取 Discord 訊息。研究者負責判斷介入時機及所有實驗決策。

## Windows 首次安裝（PowerShell）

1. 從 https://www.python.org/downloads/windows/ 安裝 **Python 3.12（64 位元）**，勾選加入 PATH。
2. 下載專案 ZIP 並解壓縮，或使用 Git 複製儲存庫。進入內層 `ai-facilitator-wizard` 資料夾，也就是有 `app.py` 的目錄。
3. 開啟 PowerShell，執行（所有後續指令均在此目錄）：

```powershell
py -3.12 --version
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --browser.gatherUsageStats false
```

不需要啟用虛擬環境或修改 PowerShell ExecutionPolicy。完成首次安裝後可雙擊 `start.bat`；終端視窗請保持開啟，結束使用時按 Ctrl+C。瀏覽器在自己電腦開啟 Streamlit 顯示的本機位址（預設埠 8501）。不要改成 `0.0.0.0` 或公開轉發連接埠。

## 先試 Demo

`.env` 預設：

```dotenv
DEMO_MODE=true
DISCORD_BOT_TOKEN=
DISCORD_CHANNELS={"示範頻道":"123456789012345678"}
DATABASE_PATH=runtime/experiments.sqlite3
```

1. 左側展開「建立實驗場次（Session）」，選擇尚未綁定的 Discord 頻道，輸入名稱、研究階段、實驗條件與備註。可自行指定唯一 Session ID，留空則使用 UUID。
2. 建立後選擇 Session，按「開始 Session」。Session 頻道建立後固定；選擇場次會自動帶入頻道，不必再次選擇目標。每個頻道只能建立一個場次（含已結束場次），切換小組時選擇另一個場次。新實驗請在 Discord 建立新的文字頻道，將 ID 加入 `.env` 的 DISCORD_CHANNELS 並重啟。Demo 建議也使用獨立頻道 ID。
3. 篩選 CPS 階段、子階段、介入類型或搜尋文字，按訊息卡片「選用／重新載入」。
4. 右側預覽可觀察徵象、原始模板及 Wizard 備註，可編輯發送內容。
5. 確認 Session、頻道 ID、內容後勾選確認，按「確認模擬發送」。應顯示 **DEMO**，不需 Token、不會呼叫 Discord API。
6. 下方可儲存獨立的觀察事件與匯出三種 CSV；觀察未介入時須填理由。
7. 要再次發送，明確按「準備下一次操作」，重新確認。完成活動後按「結束 Session」，已結束的 Session 不可繼續發送。

Demo 與正式紀錄以 `send_status=DEMO` 區分；分析時請排除 Demo。建議用獨立的 Demo Session，正式實驗亦可在 `.env` 指定不同 SQLite 檔案。變更 `.env` 後請停止並重新啟動程式；系統已存在的環境變數優先於 `.env`。

## 建立 Discord Bot 與設定正式頻道

1. 前往 https://discord.com/developers/applications ，建立 Application，在 **Bot** 頁面建立 Bot。
2. 取得／重設 **Bot Token**，只貼在自己電腦的 `.env`，勿貼入聊天、研究備註或 Git。若洩漏，立即在 Developer Portal 重設。
3. 在安裝設定或 OAuth2 URL Generator 選擇 `bot` scope，授予 **View Channels**、**Send Messages**。不需要 Administrator、使用者 Token、self-bot 或 Message Content Intent。
4. 使用產生的安裝連結，將 Bot 加入你有管理權限的測試 Discord Server。確認頻道權限覆寫沒有禁止 Bot 查看或發言。
5. Discord 使用者設定 → 進階 → 開啟「開發者模式」，在文字頻道按右鍵「複製頻道 ID」。使用一般文字頻道，第一版不處理需另外加入的執行緒。
6. 用本機文字編輯器編輯 `.env`：

```dotenv
DEMO_MODE=false
DISCORD_BOT_TOKEN=在自己的電腦填入真正的BotToken
DISCORD_CHANNELS={"測試組":"你的文字頻道ID","實驗組A":"另一個文字頻道ID"}
DATABASE_PATH=runtime/experiments.sqlite3
```

ID 必須以 JSON 字串儲存（雙引號），實際填入 17–20 位數頻道 ID。Bot Token 不需加上 `Bot ` 前綴。每次正式執行前核對介面上的模式與目標頻道。

### 正式測試第一則訊息

先使用只有研究者的測試頻道，重新啟動程式，確認畫面顯示正式模式。建立並開始「正式測試」Session，選擇一則模板，預覽後明確確認發送。成功時應顯示 `SUCCESS` 與 Discord Message ID，並到 Discord 人工確認內容、身分和頻道。程式設定 `allowed_mentions.parse=[]`，禁止文字中的 `@everyone`、角色及使用者提及意外通知。

自動化測試全用 Mock，**沒有真實 Token 時不能視為已通過 Discord 實際傳送驗收**。本次開發沒有進行真實發送。

## 發送與錯誤處理

- 正式呼叫 API 前先提交 `PENDING` 至 SQLite；資料庫寫入失敗就不發送。
- 每次操作使用唯一 ID 與資料庫主鍵，重複點擊或相同 ID 的並行操作只會呼叫一次 API。Discord 另附 nonce 與 enforce_nonce。主動建立「下一次操作」視為新發送，請勿用來盲目重試。
- `SUCCESS`：取得 Discord 訊息 ID；`FAILED`：缺少 Token、明確 HTTP 拒絕或限流；`UNKNOWN`：逾時、網路中斷、伺服器錯誤或回應不完整；`DEMO`：未連線的模擬紀錄。
- HTTP 429 顯示 Discord 提供的等待秒數（若有），不自動重試。等待限流解除後，確認原訊息未發出，再建立新操作。
- 401／403 請檢查 Token／權限，404 請檢查頻道 ID。錯誤只保存安全摘要，不保存 Authorization、原始 HTTP 回應或例外內容。
- **UNKNOWN 或程式中斷遺留的 PENDING 可能已發送**。先到 Discord 核對並以觀察紀錄補充結果，禁止直接重送。第一版不自動調和此狀態，也不自動修改歷史紀錄。
- 若送出成功但最終資料庫更新失敗，PENDING 仍會保留。重啟後不會自動再送。開始下一操作前請查閱下方歷史紀錄。

## 模板維護與研究範圍

`data/messages.json` 內含 22 則繁體中文模板（10 則常態、12 則特殊）。涵蓋 A-1、A-2、A-3、B-1、C-1，不執行 C-2。約 45 分鐘的活動時間由研究者掌握。

直接修改 JSON、新增物件即可擴充，不需更改 Python。每則包含 `message_id`、`title`、`cps_stage`、`cps_substage`、`intervention_type`、`category`、`trigger_condition`、`observable_indicators`、`content`、`wizard_notes`、`enabled`、`template_version`。ID 不可重複；`enabled` 為 JSON 布林值；類型為 routine 或 special。停用請設 `false`；修改內容時更新模板版本。程式會檢查結構與 Discord 2000 UTF-16 單位的長度限制。示範訊息僅引導程序與互動，正式研究前請依研究計畫審查模板及介入準則。

## 資料、匯出與備份

- 預設資料庫：專案下 `runtime/experiments.sqlite3`，啟動時自動初始化。Windows 重啟後以相同路徑啟動即可讀取原紀錄，請勿刪除此資料夾。
- SQLite 是正式資料來源；Session、發送操作、觀察事件分表儲存。發送保留原始模板、實際內容、編輯標記、版本與 Discord ID。
- 所有時間以含 UTC offset 的 ISO 8601 儲存，介面顯示台灣 UTC+8。CSV 保留原始 UTC 完整時間戳記。
- 每個 Session 提供「發送紀錄」「觀察紀錄」「Session 基本資料」CSV，UTF-8 with BOM，Windows Excel 可讀繁體中文；多行訊息與逗號透過 CSV quoting 保留。若自由文字以 `=` 等開頭，請以 Excel 的文字匯入方式開啟，避免將研究資料當作公式。
- 「資料庫維護」可執行 SQLite integrity_check 與 foreign_key_check，並用 SQLite backup API 建立一致備份，預設 `backups/experiments-UTC時間.sqlite3`。
- 將備份另複製至研究者管理的安全磁碟。還原時先關閉程式，保留目前資料庫副本，再以完整備份取代 `.env` 指定的資料庫，重新啟動並執行完整性檢查。
- `.gitignore` 排除 `.env`、runtime、backups、SQLite、CSV 與 log。程式不會執行 Git、上傳研究紀錄或使用外部資料儲存。SQLite 本身未加密，請使用 Windows 帳號權限與磁碟加密保護資料；不要將研究資料存進版本控制目錄中其他未忽略的路徑。

## 測試與程式結構

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

測試使用暫存 SQLite、Mock HTTP 和 Streamlit AppTest，涵蓋載入／篩選、預覽編輯、Demo 禁止 API、成功／失敗／逾時、發送前持久化、資料庫失敗禁止發送、重複操作、崩潰後 PENDING、跨 Session 隔離、CSV BOM／多行內容、重啟持久化、備份、Token 遮蔽及 UI 確認重設。

- `app.py`：單頁操作介面。
- `src/config.py`：本機設定；`discord_client.py`：REST 與安全錯誤摘要。
- `database.py`：SQLite 初始化／備份；`session_service.py`：Session 生命週期。
- `message_service.py`：模板驗證與搜尋；`logging_service.py`：發送與觀察紀錄；`export_service.py`：CSV。
- `start.bat`：Windows 啟動；`.streamlit/config.toml`：localhost 與停用使用統計。

開發與測試已在 Linux Python 3.12 執行；Windows 的批次檔與真實 Discord 發送仍需在研究者電腦做最後實機驗收。不需要雲端部署。

### 場次與頻道綁定更新

一個 Discord 文字頻道對應一場實驗，頻道選單僅在建立場次時提供尚未使用的頻道。發送預覽會顯示場次綁定的頻道名稱及 ID，切換場次會取消發送確認。若 `.env` 移除了場次頻道，舊紀錄仍可查看與匯出，但必須補回原頻道設定才能發送。

升級保留所有既有場次、發送與觀察紀錄。舊版若已有多個場次共用同一頻道，仍可選擇使用並會顯示提醒，不會合併或刪除資料；僅禁止新增重複綁定。系統仍只記錄 Wizard 操作，沒有讀取、下載或保存參與者的 Discord 對話。
