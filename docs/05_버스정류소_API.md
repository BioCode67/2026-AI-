# 버스정류소 받기 — 국토교통부 TAGO API

data.go.kr 에서 **[개발계정] 국토교통부_(TAGO)_버스정류소정보** 활용신청 후,
발급받은 **일반 인증키(Encoding)** 를 아래 `$key` 자리에 넣고 PowerShell 에서 실행합니다.

> ⚠️ 인증키는 개인 자격증명입니다. 이 문서나 코드에 저장하지 마시고,
> 실행할 때만 붙여넣어 쓰세요. 저장소에는 남기지 않습니다.

```powershell
$key = "여기에_본인_인증키(Encoding)_붙여넣기"
$svc = "https://apis.data.go.kr/1613000/BusSttnInfoInqireService"

# 1) 천안시 도시코드 찾기
$r = Invoke-RestMethod -Uri "$svc/getCtyCodeList?serviceKey=$key&_type=json"
$city = $r.response.body.items.item | Where-Object { $_.cityname -like "*천안*" }
$code = $city.citycode
Write-Host "천안 도시코드: $code"

# 2) 정류소 전체 받기
$all = @()
for ($p = 1; $p -le 30; $p++) {
  $u = "$svc/getSttnNoList?serviceKey=$key&cityCode=$code&numOfRows=1000&pageNo=$p&_type=json"
  $r = Invoke-RestMethod -Uri $u
  $items = $r.response.body.items.item
  if (-not $items) { break }
  $all += $items
  Write-Host "  page $p / 누적 $($all.Count)"
  if ($all.Count -ge [int]$r.response.body.totalCount) { break }
}
$all | Export-Csv ".\천안_버스정류소.csv" -NoTypeInformation -Encoding UTF8
Write-Host "완료: 정류소 $($all.Count)개"
```

결과 `천안_버스정류소.csv` 를 `data/raw/bus_stop.csv` 로 넣으면 됩니다.

## 왜 좌표만으로 되나

TAGO 는 정류소 **주소를 주지 않고 위경도(gpslati/gpslong)만** 줍니다.
그래서 적재기가 좌표를 받아 **가장 가까운 생활권 중심점**에 배정하도록 만들어 두었습니다
(`src/ingest.py` 의 `_transit_zones`). 어느 생활권에서도 12km 넘게 떨어진 점은
천안 밖으로 보고 제외합니다.

## 잘 안 될 때

- `getCtyCodeList` 에서 아무것도 안 나오면 → 활용신청 승인이 아직 안 난 상태입니다
  (개발계정은 보통 즉시 승인이지만 몇 분 걸릴 수 있습니다)
- `SERVICE_KEY_IS_NOT_REGISTERED_ERROR` → 승인 대기 중이거나 키를 잘못 붙여넣은 경우
- `getSttnNoList` 가 빈 결과를 주면 → 좌표 격자 조회(`getCrdntPrxmtSttnList`) 방식으로
  바꿔야 합니다. 그 경우 알려주시면 스크립트를 다시 드리겠습니다.
- 개발계정은 **일 1,000회** 호출 제한이 있습니다. 위 스크립트는 30회 이내로 끝납니다.
