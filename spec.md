# spec.md — 多步驟旅遊規劃代理（ReAct Planning Agent）

## 1. 專案概述

一個部署在雲端的 web app：使用者填表單（出發日期、天數、城市/地區、參觀偏好），後端用 LangGraph 實作的 ReAct 代理即時執行 Observation → Thought → Action → Reflection 迴圈，呼叫真實 Google API 查天氣、查景點、算交通時間，產出可行的多天行程；前端即時顯示每輪推理過程、用互動地圖呈現每天路線，行程可以儲存、也可以匯出成圖文並茂的一頁旅遊計畫。

## 2. Goals / Non-goals

**Goals**
- 實作可運作、可觀察的 ReAct 迴圈，`max_iterations = 8`
- 三個真實工具：查天氣、查景點、算交通時間，全部串真實 Google API
- 迴圈能在「時間排不下」或「查無資料」時提前優雅結束，不硬湊、不崩潰
- Web 介面即時顯示每輪四段內容，並能重播任一次歷史執行
- 部署在雲端，任何裝置（含手機）都能使用
- 行程可以儲存、可以匯出成圖文並茂的一頁計畫

**Non-goals**（本版不做）
- 使用者手動編輯 AI 排好的行程細節（要調整就重新填表單再跑一次）
- 天氣影響行程排程的決策邏輯（天氣僅供參考顯示）
- 跨城市/跨地區的多地點行程（一次規劃只針對一個城市/地區）
- 離線規劃功能（PWA 只快取靜態資源，規劃行程一定要連網）
- 完整的使用者帳號系統（只有共享密碼，不分誰是誰）
- 正式的多人流量擴展（Cloud Run 固定 1 個 instance）

## 3. 視覺設計語言

- **色彩**：暖色調為主——珊瑚橘/陽光黃當主色，天空藍當點綴色；背景用米白/淺灰，不用深色或全黑背景；卡片白底＋柔和陰影，不用銳利深色邊框
- **形狀**：圓角卡片、圓角按鈕，避免尖銳直角
- **字體**：現代無襯線字體，例如 `-apple-system, "Noto Sans TC", sans-serif`，字重適中不過粗
- **AI 封面插畫固定風格詞**（見 12.2）：「明亮、扁平插畫風格（flat illustration）、暖色調、陽光感、都市街景元素、輕鬆愉快的氛圍」
- **文案語氣**：介面文字（尤其 Reflection、`infeasible`/`no_results` 訊息）用輕鬆口語，避免生硬技術錯誤訊息
- **PWA `theme_color`**：呼應主色調（珊瑚橘）

## 4. 使用者輸入（表單規格）

| 欄位 | 型態 | 說明 |
|---|---|---|
| 出發日期 | date picker | 預設明天；若超出天氣 API 預報範圍，天氣查詢會優雅跳過 |
| 天數 | 數字輸入 | 建議限制 1～7 天 |
| 城市/地區 | 文字輸入 | 例：「台南」「花蓮」 |
| 參觀偏好 | 多選 checkbox（至少選 1 個） | 見下表 |

**偏好類別與 Google Places 對應：**

| 偏好類別 | Google Places type / 關鍵字 | 停留時間估計 |
|---|---|---|
| 博物館 | `museum`, `art_gallery` | 1.5 hr |
| 大自然風景 | `park`, `natural_feature` | 1.5 hr |
| 美食 | `restaurant`, `cafe` | 1 hr |
| 歷史古蹟 | `tourist_attraction` + 關鍵字「古蹟/歷史」 | 1 hr |
| 購物 | `shopping_mall` | 1 hr |
| 夜市/在地市集 | 關鍵字「夜市」 | 1 hr |
| 爬山 | `hiking_area` + 關鍵字「登山步道」 | 3 hr |
| 打高爾夫 | `golf_course` | 4.5 hr |
| 其他（泛用類別，非上述明確對應）| `tourist_attraction` | 1 hr（預設值） |

## 5. 外部 API 清單

| API | 用途 | 呼叫時機 |
|---|---|---|
| Geocoding API | 城市名稱 → 經緯度座標 | 準備階段 |
| Places API (New) — Text Search | 依偏好查候選景點 | 準備階段，每個偏好各一次 |
| Places Photos | 抓景點真實照片 | 行程完成（`done`）時，一次性 |
| Weather API | 查每天天氣（僅供參考） | 主迴圈第 1 輪 |
| Directions API | 算景點間真實交通時間（開車基準）、取得路線 `overview_polyline` | 主迴圈第 2 輪起 |
| Maps JavaScript API | 前端互動地圖繪製 | 前端，顯示行程時 |
| Static Maps API | 一頁計畫匯出頁的靜態地圖圖片 | 行程完成時，一次性 |
| Gemini API | `think`/`reflect` 推理（tool calling）＋ AI 封面插畫生成 | 主迴圈每輪＋行程完成時 |

所有金鑰（除 Maps JavaScript API 外）都只在後端使用，透過 Cloud Run 的 Secret Manager 整合管理。Maps JavaScript API 金鑰是唯一需要曝露在前端頁面的金鑰，需在 Google Cloud Console 設定 HTTP referrer 限制（限定部署後的 Firebase Hosting 網域）。

## 6. 技術棧與架構

- **後端**：Python 3.11+，FastAPI，LangGraph（`StateGraph`）
- **LLM**：Gemini API（文字推理 + 圖片生成）
- **前端**：純 HTML/CSS/JS（無框架），`EventSource` 接 SSE，Google Maps JavaScript API 畫互動地圖
- **部署**：Firebase Hosting（前端靜態資源）＋ Cloud Run（FastAPI 後端，`max_instances = 1`）
- **資料儲存**：Firestore（執行紀錄 `runs`、已完成行程 `trips`）
- **檔案儲存**：Firebase Storage（AI 封面插畫、快取的景點照片、Static Maps 快照）
- **存取控制**：共享密碼（shared secret）

```
travel-planner/
├── main.py                    # FastAPI app、路由、SSE endpoint、密碼驗證 middleware
├── agent/
│   ├── state.py               # PlannerState TypedDict
│   ├── graph.py                # 四個 node + 條件邊 + compile
│   └── tools.py                # 工具函式：geocode、search_places、get_weather、get_directions
├── services/
│   ├── firestore_client.py     # runs / trips 讀寫
│   ├── storage_client.py       # Firebase Storage 上傳/讀取
│   ├── image_gen.py             # Gemini 封面插畫生成
│   └── export.py                # 一頁計畫網頁產生（含 Static Maps 呼叫）
├── static/
│   ├── index.html               # 主頁（表單＋即時執行區＋結果區＋互動地圖）
│   ├── trips.html                # 已儲存的行程列表頁
│   ├── export.html               # 列印用一頁計畫頁面（@media print）
│   ├── app.js
│   ├── style.css
│   ├── manifest.json             # PWA
│   └── sw.js                     # Service worker（僅快取靜態資源）
├── requirements.txt
├── Dockerfile                    # Cloud Run 用
├── firebase.json                 # Hosting rewrites 導向 Cloud Run
└── README.md                     # 含 GCP/Firebase 專案設定步驟
```

## 7. State 結構

```python
class PlannerState(TypedDict):
    city: str
    lat: float
    lng: float
    start_date: str
    days: int
    preferences: list[str]              # 使用者選的偏好類別
    candidates: dict[str, list[dict]]   # 每個偏好類別 -> 候選景點列表（來自準備階段）
    no_results_categories: list[str]    # 完全查無資料的偏好類別

    iteration: int
    max_iterations: int                 # 固定 8
    trim_attempts: int                  # 全域調整次數，上限 2
    weather_checked: bool
    weather_notes: list[str]            # 天氣參考備註，附加在最終行程 notes

    thoughts: list[str]
    actions: list[dict]                 # {"tool": str, "input": dict}
    observations: list[dict]            # {"tool": str, "result": dict, "success": bool, "error": str | None}
    reflections: list[str]

    day_allocations: dict[str, list[dict]]  # "day1" -> [{"place_id", "name", "lat", "lng", "duration_hr", "types"}]
    day_totals: dict[str, float]            # "day1" -> 該天總時數（含交通時間）
    day_polylines: dict[str, str]            # "day1" -> Directions 回傳的 overview_polyline
    over_time_days: list[str]

    status: Literal["in_progress", "done", "infeasible", "no_results", "failed_max_iterations"]
    final_report: str | None
```

## 8. 準備階段（不計入 8 輪迴圈）

1. `geocode(city)` → 取得 `lat`, `lng`
   - 若查無此地名 → 直接進入 `no_results` 狀態，回報「找不到『{city}』，請確認地名」，不進入主迴圈
2. 對每個選中的偏好類別，各呼叫一次 `search_places(lat, lng, category)`（Places Text Search），結果存入 `candidates[category]`
   - 若某類別查無結果，記入 `no_results_categories`，但不中斷（其他類別繼續）
   - 若**全部**偏好類別都查無結果 → 進入 `no_results` 狀態，回報「找不到『{city}』符合所選偏好的景點資料」
3. 本次執行內用 `(city, category)` 當 key 做記憶體快取，避免重複呼叫

## 9. ReAct 主迴圈（`max_iterations = 8`）

```
think → act → reflect → route ─┬─ 繼續 → think
                                 ├─ 成功 → finish
                                 ├─ 不可行 → infeasible
                                 └─ 撞上限 → give_up
```

### 第 1 輪：查天氣
- `think`：決定查詢這次行程涵蓋的所有日期的天氣
- `act`：呼叫 `get_weather(lat, lng, dates)`，結果寫入 `observations`；若日期超出預報範圍，標記 `success: False`
- `reflect`：產生天氣參考備註（例：「這天可能下雨，記得帶雨具」），寫入 `weather_notes`，**不影響任何排程決策**

### 第 2 輪：初始排程與交通時間檢查
- `think`：把 `candidates` 分配到每一天，形成初始草稿 `day_allocations`
- `act`：對每一天呼叫 `get_directions`（開車基準），算出該天景點間真實交通時間與 `overview_polyline`；`day_totals[day] = Σ停留時間 + Σ交通時間`
- `reflect`：比對每天 `day_totals` 與每天可遊覽時數（8 小時），列出 `over_time_days`

### 第 3 輪起：調整
- `think`：從 `over_time_days` 挑總時數最高的一天，決定移除該天一個景點
- `act`：重新呼叫該天的 `get_directions`，更新 `day_totals[day]`，`trim_attempts += 1`
- `reflect`：檢查該天是否有改善，更新 `over_time_days`

### `route`（純邏輯判斷，依序檢查）
1. `over_time_days` 為空，且每個選中偏好都至少有一個景點出現在 `day_allocations` 中 → **`finish`**
2. `trim_attempts >= 2` 且 `over_time_days` 非空且沒有改善 → **`infeasible`**，回報哪幾天超時多久
3. `iteration >= max_iterations` → **`give_up`**（`status = failed_max_iterations`），回報目前進度與缺口
4. 其他 → 回 `think`，`iteration += 1`

## 10. 結束狀態總表

| status | 觸發條件 | 使用者看到的訊息基調 |
|---|---|---|
| `done` | 所有天數 ≤8hr 且偏好都有排進 | 顯示完整行程＋地圖 |
| `infeasible` | 2 次全域調整後仍有天數超時 | 「第 X 天排不下，超時約 Y 小時，建議減少一個偏好或增加天數」 |
| `no_results` | 城市或所有偏好都查無資料 | 「找不到符合條件的景點資料，請確認地名或換個偏好」 |
| `failed_max_iterations` | `iteration >= 8` 仍未收斂 | 「目前規劃到這裡，還缺什麼資訊」＋目前草稿 |

四種狀態的文案都要符合第 3 節的輕鬆口語風格，不用生硬的技術錯誤訊息。

## 11. 完成後處理（僅 `status == "done"` 時執行）

1. 對 `day_allocations` 裡每個景點，呼叫 Places Photos 抓一張真實照片，上傳到 Firebase Storage
2. 呼叫 Gemini 圖片生成，依固定風格 prompt（見第 3 節）產生一張以該城市為主題的封面插畫，上傳到 Firebase Storage
3. 對每一天呼叫 Static Maps API，用 `day_allocations` 座標當標記、`day_polylines[day]` 疊路線，產生靜態地圖圖片，上傳到 Firebase Storage
4. 把完整行程（含以上圖片的 Storage URL）寫入 Firestore `trips` collection
5. 送出 SSE `final` 事件，前端顯示完整結果

## 12. 儲存與匯出功能

### 12.1 已儲存的行程
- `status == "done"` 的行程自動存入 Firestore `trips`（不用使用者手動按儲存）
- 前端 `trips.html`：列表顯示每筆行程的 AI 封面縮圖、城市、天數、日期
- 因為只有共享密碼、沒有個人帳號，這是所有知道密碼的人共用的清單
- 提供刪除按鈕，避免清單變髒
- `infeasible` / `no_results` 的執行不會出現在這個清單裡（只能透過重播功能看執行過程）

### 12.2 一頁旅遊計畫匯出
- 獨立頁面 `export.html`，內容：AI 封面插畫、逐天行程文字（景點名稱、時間、真實縮圖）、每天的 Static Maps 靜態地圖
- 用 `@media print` CSS 排版成適合列印的單頁版面
- 使用者用瀏覽器內建「列印 → 儲存為 PDF」自行存檔，後端不產生 PDF 檔案

## 13. Web API 規格

| Method | Path | 說明 |
|---|---|---|
| `POST` | `/api/plan` | body `{"city", "start_date", "days", "preferences"}` → 立即回 `{"run_id"}`，背景啟動代理 |
| `GET` | `/api/plan/{run_id}/stream` | SSE，即時推送每個事件，`final` 事件後關閉連線 |
| `GET` | `/api/plan/{run_id}/replay` | 回傳該次執行的完整事件陣列（讀 Firestore，不重新呼叫 LLM/工具）|
| `GET` | `/api/runs` | 列出所有執行紀錄（`run_id`、需求、`status`、時間） |
| `GET` | `/api/trips` | 列出 `已儲存的行程`（Firestore `trips`） |
| `DELETE` | `/api/trips/{trip_id}` | 刪除一筆已儲存的行程 |
| `GET` | `/api/trips/{trip_id}/export` | 回傳一頁計畫的 HTML（`export.html` 內容） |

所有 `/api/**` 路徑都需要通過共享密碼驗證（header 或 cookie 帶密碼，比對環境變數裡的值，不對則回 401）。

SSE 事件格式：

```json
{"type": "thought" | "action" | "observation" | "reflection" | "status" | "final" | "error",
 "iteration": 2,
 "content": { ... },
 "timestamp": "2026-07-23T10:00:00Z"}
```

Agent 執行中拋出未預期例外時，後端 catch 住，送出 `type: "error"` 事件（附友善訊息）後正常關閉串流，不回 500。

## 14. 前端 UI 規格

- **首頁 `index.html`**：表單（出發日期、天數、城市、偏好 checkbox）→ 送出後即時執行區（一輪一張卡片，Thought/Action/Observation/Reflection 四色區分）→ 結果區（成功顯示逐天行程表格＋互動地圖分頁；`infeasible`/`no_results`/`failed_max_iterations` 顯示對應的橘色提示卡）
- **互動地圖**：Google Maps JavaScript API，Day 1／Day 2／… 分頁籤切換，每天疊加該天 `overview_polyline`（解碼後用 `Polyline` 畫出）＋景點 `Marker`（點擊顯示名稱、地址、預估停留時間），地圖資料重用後端已計算的結果，前端不重複呼叫 Directions API
- **`trips.html`**：已儲存的行程列表，卡片式排列（封面縮圖＋城市＋天數＋日期），可刪除
- **`export.html`**：列印用一頁計畫，`@media print` 排版
- **響應式設計**：flexbox/grid + media queries，確保手機瀏覽器操作正常
- **PWA**：`manifest.json`（含 `theme_color`）＋ `sw.js`（只快取靜態資源，不快取 API 回應），無網路時顯示「請連上網路」提示

## 15. 密碼保護

- 前端進入頁面前要求輸入密碼，正確後存入 `localStorage`（同瀏覽器不用每次重輸）
- 後端每個 `/api/**` request 檢查密碼 header/cookie，比對環境變數 `SHARED_SECRET`，不符回 401

## 16. 成本與快取

- 準備階段的 Places 查詢、主迴圈的 Directions 查詢，都在單次執行內用記憶體字典快取（key 為 `(city, category)` 或 `(place_a, place_b)`），避免同一次執行重複呼叫
- 不做跨執行的快取（保持簡單，不用資料庫層快取）
- 建議在 GCP 專案設定 Billing 預算警示，作為額外的成本安全網

## 17. 測試模式與驗收標準

### 17.1 `TEST_MODE`
環境變數 `TEST_MODE=true` 時，三個工具（Places、Weather、Directions）與 Gemini 的呼叫都改用錄製好的固定回應（fixture），不打真實 API，讓下列案例可以重複驗證且不花費用。

### 17.2 驗收標準（分層驗證）

**第一層：核心 ReAct 迴圈邏輯（用 `TEST_MODE`）**
- **案例 A（正常）**：城市＋天數＋偏好組合可行 → `status == "done"`，`iteration <= 8`，每天 `day_totals <= 8hr`，每個偏好都出現在行程中
- **案例 B（時間排不下）**：偏好組合（例如同時選「爬山」＋「打高爾夫」＋3 個其他偏好，天數只給 1 天）→ `status == "infeasible"`，`final_report` 明確列出哪天超時多久
- **案例 B2（查無資料）**：故意打錯城市名稱或選一個該城市明顯沒有的偏好 → `status == "no_results"`
- **案例 C（迴圈上限）**：用 fixture 讓 `reflect` 每輪都判定還有問題 → 在第 8 輪觸發 `failed_max_iterations`，不會無限迴圈

**第二層：雲端部署**
- Cloud Run 服務可正常啟動、`max_instances=1` 設定生效
- Firebase Hosting 能正確 rewrite `/api/**` 到 Cloud Run
- 共享密碼保護生效（無密碼或密碼錯誤回 401）
- 手機瀏覽器（響應式）與桌面瀏覽器都能正常操作；PWA 可「加到主畫面」

**第三層：儲存與匯出**
- 案例 A 成功執行後，`trips` collection 出現對應文件，`trips.html` 列表顯示該筆行程＋正確的封面縮圖
- 景點縮圖、封面插畫、Static Maps 快照都正確存在 Firebase Storage 且可讀取
- `export.html` 列印預覽版面正常，瀏覽器「列印→存PDF」可產出完整一頁計畫
- 刪除已儲存的行程功能正常運作

## 18. 交付物清單

- [ ] `agent/state.py`、`agent/graph.py`、`agent/tools.py`
- [ ] `services/firestore_client.py`、`storage_client.py`、`image_gen.py`、`export.py`
- [ ] `main.py`（FastAPI + SSE + 密碼驗證）
- [ ] `static/index.html`、`trips.html`、`export.html`、`app.js`、`style.css`、`manifest.json`、`sw.js`
- [ ] `Dockerfile`、`firebase.json`、`requirements.txt`
- [ ] `README.md`（含 GCP 專案設定步驟：啟用 7 個 API、建立 Firestore、Firebase Storage、Cloud Run 部署、環境變數/Secret 設定）
- [ ] `TEST_MODE` 的 fixture 資料與案例 A/B/B2/C 的測試腳本
- [ ] 三層驗收的實際執行證明（截圖或紀錄檔）
