# 災害データソース一覧

nkflow で利用可能な災害・自然災害関連のデータソースを整理する。
株式市場への影響度と技術的な統合難易度で分類。

---

## 実装済み

| ソース | データ種別 | S3 キー | 備考 |
|---|---|---|---|
| JMA 地震リスト | 震源地・M・最大震度 | `raw/disaster/natural/jma/earthquake_list/` | 日次取得、日付フィルタ |
| JMA 地震詳細 | 各地点震度・津波コメント | `raw/disaster/natural/jma/earthquake_detail/` | 震度4以上のみ |
| JMA 気象警報 | 警報種別・地域・ステータス | `raw/disaster/natural/jma/warning_map/` | 警報以上のみ (注意報除外) |
| JMA 津波 | 津波警報リスト | `raw/disaster/natural/jma/tsunami/` | 発表時のみ (通常は空) |
| USGS 地震 | GeoJSON (M・座標・PAGER) | `raw/disaster/natural/usgs/earthquake/` | 日本周辺 M3.0+ |

---

## 未実装データソース

### 1. 地震関連

#### P2P Earthquake API (コミュニティ運営)

| 項目 | 値 |
|---|---|
| エンドポイント | `https://api.p2pquake.net/v2/history?codes=551&limit=50` |
| 認証 | なし |
| レート制限 | 60 req/min (/history), 10 req/min (/jma) |
| 形式 | JSON |
| 遅延 | /jma は約60秒遅延 |
| 市場影響度 | 高 |
| 統合難易度 | 低 (REST JSON、認証不要) |
| 備考 | JMA データの再配信。JMA 直接取得と重複するため優先度低 |

#### Wolfx Open API (地震・緊急地震速報)

| 項目 | 値 |
|---|---|
| エンドポイント | `https://api.wolfx.jp/jma_eqlist.json` (直近50件) |
| EEW | WebSocket リアルタイム配信あり |
| 認証 | なし |
| レート制限 | 2 req/sec |
| 形式 | JSON + WebSocket |
| 市場影響度 | 高 (EEW は先物取引に直結) |
| 統合難易度 | 低 (HTTP GET) / 中 (WebSocket EEW) |
| 備考 | JMA + CENC + USGS を統合配信。日次バッチには HTTP GET で十分 |

#### DMDATA.JP (防災情報 JSON 変換)

| 項目 | 値 |
|---|---|
| URL | `https://dmdata.jp/` |
| 対象 | 緊急地震速報・震度速報・津波警報・火山情報・気象警報 |
| 認証 | **要登録 (API キー)** |
| 形式 | JSON (JMA XML からの変換) + WebSocket |
| 市場影響度 | 高 |
| 統合難易度 | 中 (登録必要、WebSocket 対応) |
| 備考 | JMA 公式 XML を JSON に変換して配信。型定義 (TypeScript) あり |

#### J-SHIS (地震ハザードステーション)

| 項目 | 値 |
|---|---|
| エンドポイント | `https://www.j-shis.bosai.go.jp/map/api/pshm/Y2024/AVR/TTL_MTTL/meshinfo.geojson?position=139.7,35.7&epsg=4326&lang=ja` |
| 提供 | NIED (防災科学技術研究所) |
| 認証 | なし |
| 形式 | JSON / GeoJSON |
| データ | メッシュ単位の地震発生確率・揺れやすさ |
| 市場影響度 | 中 (長期リスク評価向け) |
| 統合難易度 | 低 |
| 備考 | リアルタイムではなくハザード評価データ。企業拠点のリスク評価に利用可能 |

---

### 2. 気象関連

#### JMA 天気予報 JSON

| 項目 | 値 |
|---|---|
| エンドポイント | `https://www.jma.go.jp/bosai/forecast/data/overview_forecast/{AREA_CODE}.json` |
| 詳細予報 | `https://www.jma.go.jp/bosai/forecast/data/forecast/{AREA_CODE}.json` |
| 認証 | なし |
| 形式 | JSON |
| データ | 地域別天気概況・気温・降水確率 |
| 市場影響度 | 中 (交通・電力・小売に影響) |
| 統合難易度 | 低 |
| 備考 | 非公式 API (コミュニティで仕様解析済み)。地域コード例: 130000=東京 |

#### JMA 台風情報

| 項目 | 値 |
|---|---|
| ベストトラック | `https://www.jma.go.jp/jma/jma-eng/jma-center/rsmc-hp-pub-eg/trackarchives.html` |
| 形式 | テキスト (固定長フォーマット) → JSON 変換が必要 |
| データ | 緯度・経度・中心気圧・最大風速 (6時間間隔) |
| 市場影響度 | 中〜高 (物流・建設・保険に影響) |
| 統合難易度 | 中 (テキストパース必要) |
| 備考 | リアルタイムの台風予報は HTML。IBTrACS (NOAA) からも取得可能 |

---

### 3. 水害・洪水関連

#### 浸水ナビ API (国土地理院)

| 項目 | 値 |
|---|---|
| 最大浸水深 | `https://suiboumap.gsi.go.jp/shinsuimap/Api/Public/GetMaxDepth?lon={lon}&lat={lat}&grouptype={type}` |
| 破堤点 | `https://suiboumap.gsi.go.jp/shinsuimap/Api/Public/GetBreakPointMaxDepth?lon={lon}&lat={lat}` |
| 水位局 | `https://suiboumap.gsi.go.jp/shinsuimap/Api/Public/GetWaterStation` |
| 認証 | なし |
| 形式 | JSON |
| 市場影響度 | 中 (製造業・サプライチェーンに影響) |
| 統合難易度 | 低 |
| 備考 | 座標指定で浸水深を取得。企業拠点の洪水リスク評価に利用可能 |

#### 川の防災情報 (国交省)

| 項目 | 値 |
|---|---|
| URL | `https://www.river.go.jp/` |
| データ | XRAIN 高精度降雨レーダー・テレメータ水位・河川カメラ |
| 認証 | なし (基本アクセス) |
| 形式 | 一部 JSON、一部 CSV/XML |
| 市場影響度 | 中 |
| 統合難易度 | 中 (API 仕様が統一されていない) |

---

### 4. 火山関連

#### JMA 火山情報

| 項目 | 値 |
|---|---|
| URL | `https://www.jma.go.jp/bosai/volcano/` |
| データ | 噴火警戒レベル・噴火警報・監視カメラ |
| 認証 | なし |
| 形式 | **HTML** (JSON API なし) |
| 市場影響度 | 低 (観光・交通に限定的影響) |
| 統合難易度 | 高 (HTML スクレイピング必要) |
| 備考 | DMDATA.JP 経由なら JSON で取得可能 (要登録) |

---

### 5. 土砂災害

#### 土砂災害警戒情報 (JMA + 都道府県共同発表)

| 項目 | 値 |
|---|---|
| データベース | `https://agora.ex.nii.ac.jp/cps/weather/mudslides/` |
| リアルタイム地図 | `https://agora.ex.nii.ac.jp/cps/weather/mudslides-map/` |
| 形式 | XML (REST API 経由で JSON 変換可能) |
| 市場影響度 | 低〜中 |
| 統合難易度 | 中 |

---

### 6. インフラ障害

#### TEPCO 停電情報

| 項目 | 値 |
|---|---|
| URL | `https://teideninfo.tepco.co.jp/` |
| 形式 | **HTML** (JSON API なし) |
| 市場影響度 | 中 (製造業に影響) |
| 統合難易度 | 高 (HTML スクレイピング必要、ToS 要確認) |
| 備考 | 見送り |

---

### 7. 統合サービス (有料)

#### FASTALERT (JX通信社)

| 項目 | 値 |
|---|---|
| URL | `https://fastalert.jp/realtime-api` |
| データ | 地震・台風・洪水・火災・停電・交通障害を AI で統合 |
| 認証 | **有料サブスクリプション** |
| 形式 | JSON |
| 配信速度 | 数分以内 |
| 市場影響度 | 高 (複合災害のシグナル生成に最適) |
| 統合難易度 | 低 (API が整備されている) |
| 備考 | 予算がある場合の最有力候補 |

---

## 優先度マトリクス

| 優先度 | ソース | 理由 |
|---|---|---|
| **実装済み** | JMA 地震・警報・津波, USGS | コア災害データ |
| **次に追加** | Wolfx 地震 API | 無料・認証不要・JMA+CENC+USGS 統合 |
| **次に追加** | JMA 天気予報 JSON | 無料・認証不要・交通/電力影響 |
| 中期 | 浸水ナビ API | 無料・企業拠点の洪水リスク評価 |
| 中期 | J-SHIS 地震ハザード | 無料・長期リスク評価 |
| 検討 | DMDATA.JP | 高品質だが登録必要 |
| 検討 | JMA 台風 (テキスト) | パース実装が必要 |
| 将来 | FASTALERT | 有料だが最も包括的 |
| 見送り | JMA 火山 / TEPCO 停電 | JSON API なし |

---

## 株式市場への影響パターン

| 災害種別 | 影響セクター | 方向 |
|---|---|---|
| 大地震 (震度5+) | 建設 ↑、保険 ↓、被災地域の製造業 ↓ | 直後に日経全体 ↓ |
| 台風・大雨 | 物流 ↓、建設 ↑、電力 ↓、小売 ↓ | 上陸前から織り込み |
| 津波警報 | 沿岸部製造業 ↓、保険 ↓ | 即座に反応 |
| 洪水 | サプライチェーン ↓、建設 ↑ | 被害規模に依存 |
| 火山噴火 | 観光 ↓、航空 ↓ | 限定的 |
| 大規模停電 | 製造業 ↓、発電 ↑ | 復旧速度に依存 |

---

最終更新: 2026-03-06
