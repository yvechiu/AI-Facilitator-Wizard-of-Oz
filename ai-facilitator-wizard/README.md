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

1. 左側選擇目標 Discord 文字頻道，或用「在 Discord 新增文字頻道」建立模擬頻道。**不必建立、開始或結束 Session。**
2. 在左側展開「常態流程引導／特殊情境介入／通用訊息」樹狀分類，選擇子階段或情境。卡片按「編輯」或「發送至 Discord」可開啟右側預覽。
3. 右側預覽模板及 Wizard 備註，可編輯發送內容。
4. 確認頻道 ID 和內容後勾選確認，按「確認模擬發送」。應顯示 DEMO，不需 Token、不會呼叫 Discord API。
5. 下方可儲存獨立的觀察事件與匯出本頻道的發送、觀察兩種 CSV；觀察未介入時須填理由。
6. 再次發送前按「準備下一次操作」並重新確認。切換頻道會清除發送確認，歷史紀錄與匯出也跟著頻道切換。

Demo 發送以 `send_status=DEMO` 區分；新觀察紀錄的 `session_id` 以 `channel:demo:` 或 `channel:live:` 前綴區分模式。同一頻道的匯出包含該頻道所有 Wizard 紀錄，分析時請排除 Demo。可在 `.env` 指定不同 SQLite 檔案將 Demo 與正式資料完全分開。變更 `.env` 後請停止並重新啟動程式；系統已存在的環境變數優先於 `.env`。

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

先使用只有研究者的測試頻道，重新啟動程式，確認畫面顯示正式模式。選擇目標測試頻道與一則模板，預覽後明確確認發送。成功時應顯示 `SUCCESS` 與 Discord Message ID，並到 Discord 人工確認內容、身分和頻道。程式設定 `allowed_mentions.parse=[]`，禁止 `@everyone`、角色及任意使用者提及；只有設定的 TOOL_AGENT_USER_ID 可以透過明確提及被通知。

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

`data/messages.json` 內含 23 則繁體中文模板（10 則常態、6 則特殊、7 則通用）。特殊情境合併跨階段重複文案，舊紀錄中的模板 ID 與內容不變。涵蓋 A-1、A-2、A-3、B-1、C-1，不執行 C-2。約 45 分鐘的活動時間由研究者掌握。

直接修改 JSON、新增物件即可擴充，不需更改 Python。每則包含 `message_id`、`title`、`cps_stage`、`cps_substage`、`intervention_type`、`category`、`trigger_condition`、`observable_indicators`、`content`、`wizard_notes`、`enabled`、`template_version`。ID 不可重複；`enabled` 為 JSON 布林值；類型為 routine、special 或 general。跨階段的特殊情境使用 cps_stage=跨階段、cps_substage=特殊情境；通用訊息使用 cps_stage=跨階段、cps_substage=通用訊息。原本按階段分類的模板仍可載入。停用請設 `false`；修改內容時更新模板版本。程式會檢查結構與 Discord 2000 UTF-16 單位的長度限制。示範訊息僅引導程序與互動，正式研究前請依研究計畫審查模板及介入準則。

## 資料、匯出與備份

- 預設資料庫：專案下 `runtime/experiments.sqlite3`，啟動時自動初始化。Windows 重啟後以相同路徑啟動即可讀取原紀錄，請勿刪除此資料夾。
- SQLite 是正式資料來源；發送操作與觀察事件分表儲存並依頻道管理。為相容舊資料，保留 sessions 表與 session_id 欄位，新紀錄由系統自動建立內部關聯，操作上不需管理 Session。發送保留原始模板、實際內容、編輯標記、版本與 Discord ID。
- 所有時間以含 UTC offset 的 ISO 8601 儲存，介面顯示台灣 UTC+8。CSV 保留原始 UTC 完整時間戳記。
- 每個頻道提供「發送紀錄」「觀察紀錄」CSV，UTF-8 with BOM，Windows Excel 可讀繁體中文；多行訊息與逗號透過 CSV quoting 保留。若自由文字以 `=` 等開頭，請以 Excel 的文字匯入方式開啟，避免將研究資料當作公式。
- 「資料庫維護」可執行 SQLite integrity_check 與 foreign_key_check，並用 SQLite backup API 建立一致備份，預設 `backups/experiments-UTC時間.sqlite3`。
- 將備份另複製至研究者管理的安全磁碟。還原時先關閉程式，保留目前資料庫副本，再以完整備份取代 `.env` 指定的資料庫，重新啟動並執行完整性檢查。
- `.gitignore` 排除 `.env`、runtime、backups、SQLite、CSV 與 log。程式不會執行 Git、上傳研究紀錄或使用外部資料儲存。SQLite 本身未加密，請使用 Windows 帳號權限與磁碟加密保護資料；不要將研究資料存進版本控制目錄中其他未忽略的路徑。

## 測試與程式結構

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

測試使用暫存 SQLite、Mock HTTP 和 Streamlit AppTest，涵蓋載入／篩選、預覽編輯、Demo 禁止 API、成功／失敗／逾時、發送前持久化、資料庫失敗禁止發送、重複操作、崩潰後 PENDING、跨頻道隔離與舊 Session 紀錄相容、CSV BOM／多行內容、重啟持久化、備份、Token 遮蔽及 UI 確認重設。

- `app.py`：單頁操作介面。
- `src/config.py`：本機設定；`discord_client.py`：REST 與安全錯誤摘要。
- `database.py`：SQLite 初始化／備份；`session_service.py`：保留舊版資料相容介面。
- `message_service.py`：模板驗證與搜尋；`logging_service.py`：發送與觀察紀錄；`export_service.py`：CSV。
- `start.bat`：Windows 啟動；`.streamlit/config.toml`：localhost 與停用使用統計。

開發與測試已在 Linux Python 3.12 執行；Windows 的批次檔與真實 Discord 發送仍需在研究者電腦做最後實機驗收。不需要雲端部署。

## 從控制台新增 Discord 文字頻道

已移除手動建立、選擇、開始及結束 Session 的介面，不限制每個頻道的使用次數。選好頻道後即可操作，舊資料保留。

1. Bot 仍須先使用安裝連結加入指定伺服器；這一步不能由本機程式代為授權。若已加入，不必重加。
2. 為 Bot 授予「管理頻道」「管理角色」「檢視頻道」「傳送訊息」權限（不需 Administrator）。管理角色用於設定頻道權限覆寫；Bot 無法授予自己原本沒有的權限。
3. Discord 開啟開發者模式，在伺服器圖示按右鍵「複製伺服器 ID」，注意它與頻道 ID 不同。
4. 控制台左側展開「在 Discord 新增文字頻道」，輸入伺服器 ID 與頻道名稱，確認後建立。Demo 只模擬、不呼叫任何 Discord API。
5. 正式模式會在該伺服器建立一般文字頻道，並給 Bot 明確的檢視／傳送權限。Bot 已是伺服器成員，不需要另一次邀請進頻道。新頻道沿用伺服器預設的參與者權限，不自動設為私人；研究者須在 Discord 核對哪些參與者可進入。
6. 成功後新頻道自動成為目標頻道並保存在本機 SQLite，重新啟動仍可選擇，不需手動複製頻道 ID 至 .env。Demo 建立的模擬頻道不會出現在正式模式。
7. 選擇該頻道後，即可選模板、預覽與發送，不需要建立 Session。原本的 .env 預設頻道仍然可用。

建立前先保存 PENDING，同一操作不會重複呼叫建立 API。逾時、5xx 或中斷可能已成功建立，請先至 Discord 核對，系統不自動重試。若須恢復結果不明的頻道，可人工將其 ID 加到 .env。HTTP 401 檢查 Bot Token；403 檢查權限與是否已加入伺服器；429 等待限流解除後再操作。頻道建立紀錄存於 SQLite 的 channel_operations 表，可隨資料庫一起備份。系統不會抓取 Discord 歷史訊息或保存參與者對話。

### 升級後的既有資料

不會刪除或改寫舊 Session、發送或觀察紀錄。選擇原 Discord 頻道時，會同時顯示並匯出該頻道過去不同 Session 的 Wizard 紀錄，包含已結束的 Session；新操作不受舊 Session 結束狀態影響。CSV 保留 session_id 供追溯，觀察 CSV 額外附上 discord_channel_id。若舊頻道未出現在選單，將其 ID 補回 .env 的 DISCORD_CHANNELS 後重啟即可。系統仍不下載或保存 Discord 參與者對話。

## Wizard Dashboard 樹狀導覽

頂部以精簡排列保留兩個獨立計時區與 Discord 目標頻道（連線未驗證），計時區會隨頁面正常捲走，不固定浮在訊息庫上方，移除原本不可操作的實驗階段／狀態預留文字。頻道名稱與 ID 依目前選取的頻道顯示，不會寫死成某個小組。

- **整場實驗碼表**：按「開始」才從 00:00:00 累計，按「結束」後固定結果。再次按開始會從零重新計時。
- **階段倒數計時器**：點「設定分秒」輸入分鐘、秒（秒為 0–59），按開始後倒數，計時中不能改設定。零分零秒不能啟動。按結束後固定結果，可設定下一次時間再按開始。
- 倒數到零顯示「時間到」與超時時間，**不會自動停止**，仍須按結束。沒有自動發 Discord 訊息、音效或階段跳轉。
- 兩個計時器各自控制；切換分類、編輯訊息或切換頻道不會重設或停止。每秒只更新計時區，不重新整理整個訊息庫。
- 使用 monotonic 時間差計算，不依賴畫面刷新次數。結果保留在當前瀏覽器連線，**重新整理頁面、關閉連線或重啟程式可能重置計時**。目前計時結果未寫入 SQLite 或 CSV，請在離開前記下結果；原有 Wizard 發送與觀察紀錄仍照常持久保存。

左側樹狀導覽可獨立捲動，Chevron 與 Active 底色顯示展開及選取狀態：

- 常態流程引導 → 理解挑戰 → A-1／A-2／A-3；產生點子 → B-1；行動準備 → C-1。初次預設展開至 A-1，不含 C-2。
- 特殊情境介入 → 討論停滯、討論偏題、過早收斂、參與不平衡、假性共識。既有「需要釐清問題」額外保留，待研究者確認是否繼續使用；未刪除模板。
- 通用訊息 → 時間提醒（G01）、操作協助（G02）、成果確認（G05／G06）、流程說明（G03／G07）、其他通用訊息（G04）。
- 顯示名稱「討論偏題」對應原模板 category「偏離任務」，不改寫原始資料。

右側預設搜尋目前分類，支援標題、內容及顯示標籤；勾選「搜尋全訊息庫」可跨分類搜尋。搜尋不另開頁面，也不會修改實驗階段。

每張卡片保留多行文字，提供「編輯／複製／發送至 Discord」。複製會展開原生程式碼區塊，按其右上角複製圖示即可複製完整內容；預覽區另提供「複製編輯後內容」。文字不會作為 HTML 或 JavaScript 執行。

「發送至 Discord」先開啟預覽，必須確認目標頻道和訊息後才真正送出。填寫〈模板欄位〉會自動組成內容，再次變更欄位會重新產生文字，請最後手動微調。未填完整或仍含佔位文字時禁止發送。成果要求／操作說明取自原腳本，暫定成果引用成員明確內容；本次未提供或新增正式腳本。未設定 TOOL_AGENT_USER_ID 或未插入真實提及時，＠工具代理維持文字；設定並插入後可呼叫指定工具代理摘要。

同一瀏覽器連線內，切換分類、選用另一則或收合選單都保留各則草稿與填寫欄位，不覆蓋模板 JSON。重新整理或重啟可能清除尚未發送草稿；正式操作紀錄仍保存在 SQLite。每則模板／頻道／Demo 模式保留操作 ID，重新選用已送出的訊息不會再送；需要再次發送時明確按「準備下一次操作」。PENDING／UNKNOWN 仍須先人工核對 Discord。

### 模組與狀態

- `src/navigation.py`：樹狀結構、顯示標籤、既有模板映射與搜尋。新增類別或調整通用訊息歸屬在此修改，不需改寫訊息內容。無法映射的模板會進入「待確認分類」，不靜默刪除。
- `src/dashboard_state.py`：獨立的 `navigation_state`、`experiment_state`，以及每則訊息的草稿、欄位與操作 ID。導覽回呼不會寫入 `experiment_state`。
- `src/dashboard_ui.py`：樹狀元件、計時區、原生複製與低彩度樣式；`src/timers.py`：兩個獨立計時器的開始、結束與時間計算。
- `app.py`：組合元件與既有 Discord／SQLite 發送、觀察、匯出及備份流程。

本次不修改 messages.json、資料庫結構或依賴清單。沒有新增雲端服務，也不會讀取／保存 Discord 參與者對話。

## 呼叫自訂工具代理進行摘要

本次串接的是 `yvechiu/tool-agent` 現有的「@ 後摘要目前頻道」功能。`/create-board` 與 `/analyze-board` 維持人員操作的斜線指令，沒有自動轉發斜線指令或用自然語言執行任意工具。

1. Discord 開發者模式下，對「工具代理 Bot 成員」按右鍵複製**使用者 ID**，在本控制台 `.env` 新增 `TOOL_AGENT_USER_ID=1562006162856222725`（本研究工具代理 ID）。不是頻道 ID、角色 ID 或 Token。
2. 工具代理 GitHub 版本已把引導者 Bot `1560949145030893618` 加入白名單，不需設定先前提議的 FACILITATOR_BOT_ID。確認本控制台的 Bot Token 屬於這隻引導者 Bot。
3. 兩隻 Bot 均加入同一個伺服器、能查看及發送到目標頻道。工具代理須依原說明啟用 Message Content Intent、設定 Gemini 並保持執行；引導者仍不需讀取參與者訊息。更改 .env 後重啟兩個程式。
4. 先測 Demo：通用訊息 → 其他通用訊息 → 請工具代理整理 → 填整理範圍 →「插入工具代理提及」。預覽會出現 `<@使用者ID>`，確認模擬發送後只存 DEMO，不呼叫任何 Bot。
5. 實際測試：關閉 Demo 並重啟，在私人測試頻道先讓成員發言，再依相同步驟確認發送。工具代理會摘要該頻道已接收到的討論並回覆；Gemini 可能產生 API 費用。工具代理請更新至你已推送的白名單版本，引導者套用本次 REST 發送改動。

Wizard 只發出請求、不下載參與者對話。工具代理沿用既有的每頻道記憶體紀錄，只整理啟動後已收到的內容；目前工具代理會摘要本頻道自啟動後已收集的全部參與者對話，不會把引導者請求中的整理範圍另外交給摘要模型，因此不可視為範圍過濾。引導者請求不計入成員參與度。工具代理新版僅開放指定引導者 Bot 的摘要呼叫，忽略其他 Bot 與自身訊息；引導者沿用操作 ID 與 nonce 防止重複送出。此處採用工具代理現有白名單版本，不覆蓋它的程式。
