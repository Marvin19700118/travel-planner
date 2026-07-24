# 行程規劃助手（Travel Planner）

*[Read this in English](README.md)*

一個採用 ReAct 模式的 AI 代理人，協助規劃多天行程。完整的產品規格請見 [spec.md](spec.md)，工作拆分請見 GitHub issues。

已完成的部分：[#2](https://github.com/Marvin19700118/travel-planner/issues/2)（核心迴圈、`TEST_MODE` 假資料）、[#3](https://github.com/Marvin19700118/travel-planner/issues/3)（真實 Google API + Gemini 整合，走同一個 seam）、[#4](https://github.com/Marvin19700118/travel-planner/issues/4)（互動地圖）、部分 [#5](https://github.com/Marvin19700118/travel-planner/issues/5)（共享密碼 + 部署相關檔案 —— 首次真實部署還缺什麼請見下方「部署」一節）、[#6](https://github.com/Marvin19700118/travel-planner/issues/6)（手機響應式設計 + PWA）、[#7](https://github.com/Marvin19700118/travel-planner/issues/7)（自動儲存行程、附真實照片與 AI 封面插畫、已儲存行程列表頁）、[#8](https://github.com/Marvin19700118/travel-planner/issues/8)（一頁式可列印匯出，含每日靜態地圖），以及 [#9](https://github.com/Marvin19700118/travel-planner/issues/9)（重播任何一次歷史紀錄，不論成功與否，且不會產生任何新的外部呼叫）。

**給接下來要修改 `static/style.css`、`static/app.js`、`static/manifest.json` 或圖示檔案的人：** 記得在 `static/sw.js` 中把 `CACHE_NAME` 加一版。Service worker 會用這個名稱快取那些檔案；不加版號的話，已經安裝過的瀏覽器會一直沿用改動前快取的內容，永遠不會更新。這個問題在開發 #6 時讓我踩了兩次坑 —— CSS 和 JS 的修正在已經裝過舊版的瀏覽器裡完全沒生效，直到我把快取名稱加了版號才解決。

## 安裝

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 環境變數

| 變數 | 何時需要 | 說明 |
|---|---|---|
| `TEST_MODE` | 一定需要 | `true` 時完全跑假資料（不需要網路、不需要金鑰）；`false` 時呼叫真實 Google API |
| `GOOGLE_MAPS_API_KEY` | `TEST_MODE=false` 時 | 需要在同一個 Google Cloud 專案上啟用 Geocoding API、Places API (New)、Directions API、Weather API |
| `GEMINI_API_KEY` | 選填，僅在 `TEST_MODE=false` 時使用 | 若未設定，Thought/Reflection 文字會退回 `TEST_MODE` 使用的同一套固定字串，AI 封面插畫也會改用真實景點照片代替 —— 就算沒有這個金鑰，只要有真實的景點/天氣/路線資料，整個 app 仍然完全可用 |
| `GOOGLE_MAPS_JS_API_KEY` | 要顯示互動地圖，或匯出頁的每日靜態地圖時 | 刻意與 `GOOGLE_MAPS_API_KEY` **分開**的另一個金鑰 —— 這個會暴露在瀏覽器端。需要在這個金鑰上**同時**允許 Maps JavaScript API（互動地圖，ticket #4）**與** Maps Static API（每日匯出地圖，ticket #8），並在 Cloud Console 設定 HTTP 參照網址限制，才能安全用在正式環境（本機開發不受影響）。若未設定，地圖區域會顯示「地圖尚未在此部署設定。」而不是一片空白；若已設定但缺少某個 API 的授權，那個地圖會退回同樣的文字提示，而不是顯示壞掉的圖片 —— 詳見下方 #8 的即時驗證紀錄 |
| `SHARED_SECRET` | 要求使用者輸入密碼才能使用這個 app 時 | 選用，跟其他設定一樣：不設定就是開放存取（本機開發、現有測試都不需要改動）。部署到任何公開環境前務必設定 —— 詳見下方「部署」一節 |

**已於 2026-07-24 用真實金鑰做過即時驗證**，包含透過部署後的 app 完整跑過一次真實的行程規劃（台北）—— 實際的上線網址與部署時發現的問題請見下方「部署」一節：
- Geocoding、Places API (New) Text Search、Directions 都已確認在真實資料下正常運作。
- `agent/tools.py` 的 `search_places` 現在把結果數上限設為 `_MAX_RESULTS_PER_CATEGORY = 5`（透過 Places API 的 `pageSize`）—— 這是即時驗證時發現的真實 bug：Text Search 預設每次查詢最多回傳 20 筆結果，而 `agent/graph.py` 的刪減迴圈（只針對小型假資料開發與測試過，每次迭代只刪一項，上限 8 次迭代）在面對兩個偏好產生的 30～40 筆真實候選地點時，完全沒辦法收斂。加上這個上限之前，每次真實執行都會以 `failed_max_iterations` 失敗收場。
- 第一次即時測試時，`weather.googleapis.com` 回傳 `403 PERMISSION_DENIED` / `API_KEY_SERVICE_BLOCKED` —— Weather API 已經在 GCP 專案上啟用，但這個金鑰在 Cloud Console 的 API 限制清單裡沒有列入。這不會導致整個流程失敗（天氣只是參考資訊，而且本來就有優雅降級的設計 —— 見 `agent/graph.py` 的 `act()` 對 Directions 失敗的處理），但要把 Weather API 加進金鑰的允許清單才能真的看到天氣預報。
- `agent/llm.py` 的 Gemini 整合使用 `google-genai` SDK。`gemini-2.0-flash` 和 `gemini-2.0-flash-preview-image-generation` 兩個模型其實都已經停用（回傳 `404 NOT_FOUND`，訊息是「no longer available」，即使 `models.list()` 裡仍然列得出來）—— 已改用 `gemini-3.1-flash-lite` / `gemini-3.1-flash-image`（依維護者偏好選用 3.1 系列），兩者都已在真實部署中端到端驗證成功，包含產生出一筆真實的已儲存行程，附上真實景點照片與真實 AI 封面插畫。
- 地圖（`static/app.js`）部署前用一個佔位金鑰驗證過：日期分頁籤、標記／路線繪製邏輯、腳本載入都正常運作。尚未針對部署後真正使用的 `GOOGLE_MAPS_JS_API_KEY` 在瀏覽器裡重新驗證過（只用 `curl` 確認過這個金鑰本身對 Maps JavaScript API 是有效的）——值得花點時間用瀏覽器實際檢查一次。另外，`google.maps.Marker` 在上游已被標示為棄用，建議改用 `AdvancedMarkerElement`；這裡先維持原樣，因為要遷移需要從 Cloud Console 另外申請一個 Map ID（又是一個新的設定步驟），而且 `Marker` 目前仍完全受支援，官方也還沒公告停止支援的時間。
- **#8 的 Static Maps API**：即時測試時，部署所用的 `GOOGLE_MAPS_JS_API_KEY` 回傳了 `403`（「This API key is not authorized to use this service or API」）—— 跟上面 Weather 金鑰限制屬於同一類問題，只是換了另一組金鑰／API。因應這個狀況強化了 `static/export.js`：靜態地圖圖片載入失敗時（`<img onerror>`）現在會換成跟「地圖尚未設定」一樣的文字提示，而不是在列印頁面留下一張壞圖示，所以這裡會優雅降級而不是顯得像壞掉一樣 —— 但要在 Cloud Console 把 Maps Static API 加進這個金鑰的允許清單，才能在匯出頁看到真正的每日路線地圖。

## 本機執行

```bash
.venv\Scripts\python.exe run_dev.py
```

然後打開 http://127.0.0.1:8000。`run_dev.py` 預設會強制設定 `TEST_MODE=true`（不需要任何金鑰）。等你有金鑰之後，可以這樣試試真實 API 的路徑：

```bash
set TEST_MODE=false
set GOOGLE_MAPS_API_KEY=your-key
set GEMINI_API_KEY=your-key
.venv\Scripts\python.exe -m uvicorn main:app --reload
```

在 `TEST_MODE=true` 底下，可以在表單裡輸入以下城市名稱來觸發每一種終止狀態：

| 城市 | 要選的偏好 | 天數 | 結果 |
|---|---|---|---|
| `testville` | museum、food | 2 | `done`（完成） |
| `sprawlville` | hiking、golf | 1 | `infeasible`（安排不下） |
| `emptyville` | 任意 | 1 | `no_results`（無結果） |
| `loopville` | food | 1 | `failed_max_iterations`（用完嘗試次數） |
| 其他任意名稱 | 任意 | 任意 | `no_results`（無法辨識的城市） |

## 部署

**已於 2026-07-24 正式上線**：https://city-explorer-acj8x.web.app（有密碼保護 —— 請向維護者取得，密碼不會存放在版本庫裡）。GCP 專案 `city-explorer-acj8x`，Cloud Run（`travel-planner-api`，`us-central1`）+ Firebase Hosting。這次實際跑過一遍真實部署，抓出並修好了兩個真正的部署問題 —— 都記錄在下面，因為任何人重新部署這個專案時都可能會踩到同樣的坑。第三個真實 bug（上方「即時驗證」一節提到的 Places 結果數上限）也是這次首次部署發現的，但它改在 `agent/tools.py` 裡，跟部署設定本身無關。

**為什麼 `firebase.json` 的 `public` 指向空白的 `hosting-public/` 目錄，而不是 `static/`**：`auth.py` 裡的共享密碼機制是 FastAPI middleware —— 只有真正打到 FastAPI app 的請求才會經過它。原本的設計把 `"public"` 指向 `static/`，想法是萬用改寫規則（`"source": "**"`）反正會把所有請求都導到 Cloud Run。這個想法是錯的：Firebase Hosting 的路由優先權永遠是「已上傳的靜態檔案優先於改寫規則」，不管改寫規則的萬用字元寫得多寬 —— 這是即時驗證出來的（`curl` 顯示真正的 `index.html`／`style.css`／`trips.html` 直接從 Hosting 的 Fastly CDN 送出，帶著 `X-Cache: HIT`，完全沒經過 Cloud Run，也就沒經過密碼檢查；只有找不到對應靜態檔案的路徑，例如 `/api/trips`，才真的會走到改寫規則）。把 `public` 指向一個空目錄，就能保證沒有任何請求會命中靜態檔案，所有流量都會落到改寫規則 → Cloud Run → `auth.py`。現在 Hosting 純粹只是 CDN／HTTPS 的門面；真正的 `static/` 資源是由 `main.py` 自己的 `StaticFiles` 掛載點提供，跟其他所有東西一樣受同一套驗證 middleware 保護。

**為什麼 `auth.py` 裡的驗證 cookie 一定要命名為 `__session`，不能取個更有意義的名字**：Firebase Hosting 的 CDN 在把請求轉發給 Cloud Run 之前，會把除了一個特別命名為 `__session` 的 cookie 之外的其他所有 cookie 都拿掉 —— 這是[官方文件記載的行為](https://firebase.google.com/docs/hosting/manage-cache)，不是我們這邊的 bug。這只影響 GET/HEAD（Hosting 的 CDN 快取層真正會處理的方法）；POST 永遠不會經過快取，所以 cookie 一直都能正常轉發。修好之前的即時症狀：登入正常、`POST /api/plan` 正常，但透過 Hosting 網址打 `GET /api/plan/{run_id}/stream` 和其他所有 GET 端點都會回 401 —— 直接打 Cloud Run 網址（跳過 Hosting）則一切正常，這就是判斷出問題出在 Hosting 層的 header 過濾、而不是 `auth.py` 本身的關鍵線索。任何要經過 Firebase Hosting 的東西，這個 cookie 名稱都必須維持 `__session`。

首次部署步驟：

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com
# 到 Cloud Console 的「APIs & Services」頁面手動啟用 Geocoding API、
# Places API (New)、Directions API、Weather API，不要在這裡用猜的
# `gcloud services enable` 識別碼 —— 我沒有十足信心能給出正確的服務
# 名稱（例如 geocoding-backend.googleapis.com 還是
# geocoding.googleapis.com），寧可請你直接在 Console 裡按「啟用」。

# 建置並部署 API 到 Cloud Run，固定為單一執行個體（見 ticket #5
# 的驗收標準：同一次執行的即時串流與背景推理程序必須永遠對應到
# 同一個執行個體）：
gcloud run deploy travel-planner-api \
    --source . \
    --region us-central1 \
    --max-instances=1 \
    --min-instances=0 \
    --allow-unauthenticated \
    --set-env-vars TEST_MODE=false,SHARED_SECRET=your-password,GOOGLE_MAPS_JS_API_KEY=your-js-key \
    --set-secrets GOOGLE_MAPS_API_KEY=google-maps-api-key:latest,GEMINI_API_KEY=gemini-api-key:latest

# 接著部署 Hosting（firebase.json 裡的 serviceId/region 必須跟上面
# gcloud 部署時用的一致）：
firebase login
firebase use --add          # 會用你的專案 ID 建立 .firebaserc
firebase deploy --only hosting
```

**`--allow-unauthenticated` 是必要的，不是可省略的選項**：Cloud Run 預設會用 IAM 擋掉每個請求，*在*請求抵達這個 app 自己的 `auth.py` 密碼 middleware *之前*就先擋掉了。沒有這個參數，任何人都無法連上這個 app —— 就算輸入了正確的 `SHARED_SECRET` 也不行 —— 因為 Cloud Run 自己的關卡會先回 403。這個 app 真正的存取控制是 `SHARED_SECRET`；`--allow-unauthenticated` 只是讓請求能通過，走到真正做檢查的地方。

**`GOOGLE_MAPS_JS_API_KEY` 一定要放在 `--set-env-vars` 裡** —— 這點很容易漏掉，因為它看起來應該跟另外兩個走 Secret Manager 的金鑰放在一起，但 `/api/config` 是直接從環境變數讀取它；漏掉的話會悄悄地回傳一個空字串，地圖在部署後的網站上完全不會顯示。

`GOOGLE_MAPS_API_KEY` 和 `GEMINI_API_KEY` 建議優先用 Secret Manager（`--set-secrets`）而不是 `--set-env-vars` —— 它們是真正的憑證。`GOOGLE_MAPS_JS_API_KEY` 是唯一的例外：它本來就打算讓瀏覽器看到，所以用一般環境變數沒問題，但部署前務必在 Cloud Console 用 HTTP 參照網址限制它（最好也限制只能用在 Maps JavaScript API）到 Hosting 的網域 —— 沒有限制的金鑰一旦被從網頁原始碼中取走，就能被拿去對任何它被允許呼叫的 API 亂用，累積用量費用。

**延後到這次首次部署之後才處理的事項**（不影響已完成的其他功能）：
- `storage.py` 目前仍是本機 JSONL 檔案，還不是 Firestore。Cloud Run 的檔案系統是暫時性的，所以在換成 Firestore 之前，重新部署或冷啟動都會讓執行紀錄消失。所有呼叫端都已經統一透過 `storage.save_run`／`load_run`／`list_runs`，所以換成 `google-cloud-firestore` 應該只需要改這一個檔案 —— 只是在沒有真正的 Firestore 實例可用時，沒辦法真的動手做並驗證（本機也沒有模擬器可用：Firebase CLI 需要 Java 執行環境，這裡也沒裝）。
- `trips.py`（已儲存的行程）和 `image_store.py`（景點／封面照片，來自 #7）也是同樣的狀況：兩者都是本機檔案系統，用來暫代 Firestore 和 Firebase Storage，原因跟上面一樣（暫時性檔案系統）。所有呼叫端都統一透過 `trips.save_trip`／`list_trips`／`delete_trip` 和 `image_store.save_image`／`read_image`／`delete_trip_images`，所以一旦有了真正的 Firestore／Storage 憑證，每一個都應該可以獨立替換。
- 上面的 `--max-instances=1` 參數才是真正滿足「同一次執行的即時串流與背景推理程序必須永遠對應到同一個執行個體」這個需求的關鍵（`main.py` 裡的記憶體內 `_run_queues` 字典在多個執行個體之間是不共享的）—— 這是部署時的參數設定，不是程式碼裡強制保證的東西，所以之後重新部署時很容易忘記加上。

## 測試

```bash
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m mypy agent/ main.py storage.py auth.py image_store.py trips.py --ignore-missing-imports
```

所有測試都不需要真實金鑰：假資料測試會設定 `TEST_MODE=true`，真實 API／Gemini 的測試則是在 HTTP／SDK 的邊界上做 monkeypatch。密碼驗證的測試會在每個測試裡自行設定／取消 `SHARED_SECRET`；不需要真正的伺服器或真實的 cookie 環境。

## 專案結構

- `agent/state.py` —— `PlannerState`、`TripRequest`，以及 `RunCache`（單次執行內的工具呼叫記憶體快取）
- `agent/tools.py` —— 唯一的 seam：`TEST_MODE` 會在假資料與真實 HTTP 實作之間切換每一個外部呼叫
- `agent/fixtures.py` —— 上面提到的四種情境假資料
- `agent/llm.py` —— Gemini 驅動的 Thought/Reflection 敘述，沒有金鑰時會退回固定字串（工具*選擇*本身永遠是確定性邏輯 —— 詳見模組內的說明文件）
- `agent/graph.py` —— LangGraph 迴圈（`think` → `act` → `reflect` → 路由）以及驅動整個迴圈的 `run_planner()` generator
- `storage.py` —— 本機 JSONL 執行紀錄儲存（**尚未換成 Firestore** —— 詳見「部署」一節）
- `trips.py` —— 本機 JSON 儲存已自動儲存完成的行程，並負責抓取真實景點照片與 AI 封面插畫的加值處理；也會原封不動存下 `day_polylines`，讓匯出頁（#8）不需要再多打一次 Directions（**尚未換成 Firestore** —— 詳見「部署」一節）
- `image_store.py` —— 本機檔案系統儲存景點／封面照片（**尚未換成 Firebase Storage** —— 詳見「部署」一節）
- `auth.py` —— 共享密碼機制（cookie 檢查、登入頁面、登入處理）
- `main.py` —— FastAPI app：密碼 middleware、`POST /api/plan`、`GET /api/plan/{run_id}/stream`（SSE）、`GET /api/plan/{run_id}/replay`、`GET /api/runs`、`GET /api/config`、`GET /api/trips`、`GET /api/trips/{trip_id}`、`DELETE /api/trips/{trip_id}`、`GET /images/{trip_id}/{filename}`、`POST /login`
- `static/` —— 純 HTML/CSS/JS 前端，響應式設計最小支援到 375px 的手機螢幕寬度
- `static/viewer.js` —— 即時畫面與重播畫面共用的渲染邏輯（步驟列表、結果、互動地圖），確保兩者的畫面永遠不會不一致
- `static/trips.html`、`static/trips.js` —— 已儲存行程列表頁（封面圖、城市、天數、刪除、匯出連結）
- `static/runs.html`、`static/runs.js` —— 所有歷史紀錄（不論結果如何），各自連結到對應的重播頁（ticket #9）
- `static/replay.html`、`static/replay.js` —— 透過 `viewer.js` 的渲染邏輯，逐步重播一次已儲存執行紀錄的每個事件，每個步驟間有短暫延遲；不會呼叫任何外部景點／天氣／路線／LLM 服務，只會呼叫這個 app 自己的 `/api/plan/{run_id}/replay`
- `static/export.html`、`static/export.js` —— 一頁式可列印行程：封面圖、逐天景點列表附真實縮圖、每天一張 Static Maps API 地圖圖片（ticket #8）
- `static/manifest.json`、`static/icon-*.png` —— PWA manifest 與圖示（珊瑚色底上一個簡單的太陽圖案，呼應整體視覺風格）
- `static/sw.js` —— 只快取靜態外殼的 service worker（絕不快取 API 回應）；詳見上方 `CACHE_NAME` 的說明
- `Dockerfile`、`.dockerignore` —— Cloud Run 容器建置設定（尚未實際建置測試過 —— 本機沒有 Docker）
- `firebase.json` —— Hosting 設定，萬用改寫規則導向 Cloud Run（原因詳見「部署」一節）
