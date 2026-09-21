$ErrorActionPreference = "Continue"
$api = "http://127.0.0.1:8010"
$web = "http://localhost:3000"
$pass = "demo123"
$ok = 0
$fail = 0

function Note([string]$who, [string]$what, [bool]$good, [string]$extra = "") {
  $script:ok += [int]$good
  $script:fail += [int](-not $good)
  $mark = if ($good) { "PASS" } else { "FAIL" }
  $line = "{0,-22} {1,-40} {2} {3}" -f $who, $what, $mark, $extra
  Write-Output $line
}

function Login([string]$email) {
  $body = '{"email":"' + $email + '","password":"' + $pass + '"}'
  $r = Invoke-RestMethod -Uri "$api/v1/auth/login" -Method POST -ContentType "application/json; charset=utf-8" -Body $body
  return @{ user = $r.data.user; token = $r.data.token; h = @{ Authorization = ("Bearer " + $r.data.token); "Content-Type" = "application/json" } }
}

function GetJson($url, $headers = $null) {
  if ($headers) { return Invoke-RestMethod -Uri $url -Headers $headers }
  return Invoke-RestMethod -Uri $url
}

function PostRaw($url, $headers, [string]$json) {
  return Invoke-RestMethod -Uri $url -Method POST -Headers $headers -Body $json
}

$pages = @(
  "/ru", "/ru/catalog", "/ru/materials", "/ru/materials/pesok-rechnoy",
  "/ru/specialists", "/ru/specialists/bek-architecture",
  "/ru/plots/izhs-besagash-gaz", "/ru/login", "/ru/site", "/ru/site/pr-besagash",
  "/ru/crm", "/ru/chat", "/ru/cabinet", "/ru/publish", "/ru/moderation",
  "/ru/compare?ids=p-besagash,p-medeu", "/kk"
)
foreach ($p in $pages) {
  try {
    $r = Invoke-WebRequest -Uri ($web + $p) -UseBasicParsing
    Note "web" $p ($r.StatusCode -eq 200) ([string]$r.StatusCode)
  } catch {
    Note "web" $p $false $_.Exception.Message
  }
}

try { $plots = GetJson "$api/v1/plots"; Note "public" "GET plots" ($plots.total -ge 1) ("n=" + $plots.total) } catch { Note "public" "GET plots" $false }
try { $mats = GetJson "$api/v1/materials"; Note "public" "GET materials" ($mats.data.Count -ge 1) ("n=" + $mats.data.Count) } catch { Note "public" "GET materials" $false }
try { $sp = GetJson "$api/v1/specialists"; Note "public" "GET specialists" ($sp.data.Count -ge 1) ("n=" + $sp.data.Count) } catch { Note "public" "GET specialists" $false }
try { $site = GetJson "$api/v1/site/projects"; Note "public" "GET site projects" ($site.data.Count -ge 1) ("n=" + $site.data.Count) } catch { Note "public" "GET site projects" $false $_.Exception.Message }

$newPlot = $null
$newRfi = $null

try {
  $b = Login "buyer@demo.superapp"
  Note "buyer" "login JWT" ($null -ne $b.token)
  $me = GetJson "$api/v1/auth/me" $b.h
  Note "buyer" "GET /me" ($me.data.role -eq "buyer") $me.data.role
  PostRaw "$api/v1/cabinet/favorites/p-besagash" $b.h "{}" | Out-Null
  Note "buyer" "favorite plot" $true
  $inq = PostRaw "$api/v1/plots/p-besagash/inquiries" $b.h '{"name":"Aliya","phone":"+77771002030","message":"view Saturday"}'
  Note "buyer" "inquiry plot" ($null -ne $inq.data.id) $inq.data.id
  $ord = PostRaw "$api/v1/specialists/sp-arch/orders" $b.h '{"specialist_id":"sp-arch","plot_id":"p-besagash","message":"sketch 180m2"}'
  Note "buyer" "order architect" ($null -ne $ord.data.id) $ord.data.id
  $mo = PostRaw "$api/v1/material-orders" $b.h '{"material_id":"mat-sand","qty":12,"address":"Besagash"}'
  Note "buyer" "order sand 12t" ($mo.data.amount_kzt -gt 0) ([string]$mo.data.amount_kzt)
  $th = GetJson "$api/v1/chat/threads" $b.h
  Note "buyer" "chat threads" ($th.data.Count -ge 1) ("n=" + $th.data.Count)
  if ($th.data.Count -gt 0) {
    $tid = $th.data[0].id
    $msg = PostRaw "$api/v1/chat/threads/$tid/messages" $b.h '{"text":"demo waiting quote"}'
    Note "buyer" "chat send" ($null -ne $msg.data.id)
  }
  $deals = GetJson "$api/v1/crm/deals?funnel=design" $b.h
  Note "buyer" "CRM design deals" $true ("n=" + $deals.data.Count)
  $favs = GetJson "$api/v1/cabinet/favorites" $b.h
  Note "buyer" "cabinet favorites" $true ("n=" + $favs.data.Count)
} catch { Note "buyer" "flow" $false $_.Exception.Message }

try {
  $o = Login "owner@demo.superapp"
  Note "owner" "login JWT" ($null -ne $o.token)
  $mine = GetJson "$api/v1/cabinet/plots" $o.h
  Note "owner" "my plots" ($mine.data.Count -ge 1) ("n=" + $mine.data.Count)
  $body = '{"cadastral_no":"20-111-222-333","title_ru":"Demo plot owner","title_kk":"Demo","district":"Talgar","purpose":"izhs","area_sotka":6,"price_kzt":12000000,"polygon":[[43.21,76.91],[43.21,76.92],[43.22,76.92],[43.21,76.91]],"gas":"connected","electricity":"connected"}'
  $created = PostRaw "$api/v1/cabinet/plots" $o.h $body
  Note "owner" "publish plot" ($created.data.status -eq "pending") $created.data.id
  $newPlot = $created.data.id
  $in = GetJson "$api/v1/cabinet/inquiries" $o.h
  Note "owner" "incoming inquiries" $true ("n=" + $in.data.Count)
} catch { Note "owner" "flow" $false $_.Exception.Message }

try {
  $md = Login "moderator@demo.superapp"
  Note "moderator" "login JWT" ($null -ne $md.token)
  $q = GetJson "$api/v1/moderation/queue" $md.h
  Note "moderator" "moderation queue" ($q.data.Count -ge 1) ("n=" + $q.data.Count)
  if ($newPlot) {
    $ap = PostRaw "$api/v1/moderation/$newPlot" $md.h '{"action":"approve","comment":"ok demo"}'
    Note "moderator" "approve new plot" ($ap.data.status -eq "published") $ap.data.status
  }
} catch { Note "moderator" "flow" $false $_.Exception.Message }

try {
  $a = Login "architect@demo.superapp"
  Note "architect" "login JWT" ($null -ne $a.token)
  $ords = GetJson "$api/v1/orders" $a.h
  Note "architect" "service orders" $true ("n=" + $ords.data.Count)
  $open = @($ords.data | Where-Object { $_.status -ne "completed" } | Select-Object -First 1)
  if ($open -and $open.id) {
    $st = Invoke-RestMethod -Uri "$api/v1/orders/$($open.id)/status?status=quoted&quote_kzt=450000" -Method POST -Headers $a.h
    Note "architect" "quote order" ($st.data.status -eq "quoted") $st.data.status
  } else { Note "architect" "quote order" $true "none open" }
  $de = GetJson "$api/v1/crm/deals?funnel=design" $a.h
  Note "architect" "CRM design" $true ("n=" + $de.data.Count)
} catch { Note "architect" "flow" $false $_.Exception.Message }

try {
  $sv = Login "surveyor@demo.superapp"
  Note "surveyor" "login JWT" ($null -ne $sv.token)
  $ords = GetJson "$api/v1/orders" $sv.h
  Note "surveyor" "orders" $true ("n=" + $ords.data.Count)
  $th = GetJson "$api/v1/chat/threads" $sv.h
  Note "surveyor" "chat" $true ("n=" + $th.data.Count)
} catch { Note "surveyor" "flow" $false $_.Exception.Message }

try {
  $c = Login "contractor@demo.superapp"
  Note "contractor" "login JWT" ($null -ne $c.token)
  $dl = PostRaw "$api/v1/site/projects/pr-besagash/daily" $c.h '{"day":"2026-09-17","workers":8,"notes":"formwork demo","weather":"clear","temp_c":22}'
  Note "contractor" "daily log" ($null -ne $dl.data.id) $dl.data.id
  $rfi = PostRaw "$api/v1/site/projects/pr-besagash/rfis" $c.h '{"title":"demo RFI floor","question":"confirm FFL","drawing":"AR-01"}'
  Note "contractor" "create RFI" ($rfi.data.number -like "RFI-*") $rfi.data.number
  $newRfi = $rfi.data.id
  $pu = PostRaw "$api/v1/site/projects/pr-besagash/punches" $c.h '{"title":"demo fence gap","location":"axis A","trade":"HSE"}'
  Note "contractor" "punch item" ($null -ne $pu.data.id)
  $ts = PostRaw "$api/v1/site/projects/pr-besagash/timesheets" $c.h '{"day":"2026-09-17","crew":"concrete/4","hours":32,"cost_kzt":160000}'
  Note "contractor" "timesheet" ($ts.data.hours -eq 32)
  $co = PostRaw "$api/v1/site/projects/pr-besagash/changes" $c.h '{"title":"demo CO sand","amount_kzt":80000,"reason":"extra"}'
  Note "contractor" "change order" ($co.data.number -like "CO-*") $co.data.number
  $crmc = GetJson "$api/v1/crm/deals?funnel=construction" $c.h
  Note "contractor" "CRM construction" $true ("n=" + $crmc.data.Count)
} catch { Note "contractor" "flow" $false $_.Exception.Message }

try {
  $n = Login "supervisor@demo.superapp"
  Note "supervisor" "login JWT" ($null -ne $n.token)
  $ins = PostRaw "$api/v1/site/projects/pr-besagash/inspections" $n.h '{"title":"demo formwork inspect","result":"pass","inspector":"Marat","day":"2026-09-17","notes":"ok","checklist":["geometry","oil"]}'
  Note "supervisor" "inspection pass" ($ins.data.result -eq "pass")
  $inc = PostRaw "$api/v1/site/projects/pr-besagash/incidents" $n.h '{"title":"demo near miss","severity":"low","description":"no helmet","actions":"briefing","day":"2026-09-17"}'
  Note "supervisor" "incident" ($null -ne $inc.data.id)
  if ($newRfi) {
    $ans = PostRaw "$api/v1/site/rfis/$newRfi/answer" $n.h '{"answer":"FFL +150 see KJ-01"}'
    Note "supervisor" "answer RFI" ($ans.data.status -eq "answered") $ans.data.status
  }
} catch { Note "supervisor" "flow" $false $_.Exception.Message }

try {
  $u = Login "supplier@demo.superapp"
  Note "supplier" "login JWT" ($null -ne $u.token)
  $skus = GetJson "$api/v1/cabinet/materials" $u.h
  Note "supplier" "my SKUs" ($skus.data.Count -ge 1) ("n=" + $skus.data.Count)
  $add = PostRaw "$api/v1/materials" $u.h '{"title_ru":"demo keramzit","category":"inert","unit":"m3","price_kzt":9000,"min_qty":5,"stock":40}'
  Note "supplier" "add SKU" ($null -ne $add.data.id) $add.data.slug
  $mos = GetJson "$api/v1/material-orders" $u.h
  Note "supplier" "incoming material orders" ($mos.data.Count -ge 1) ("n=" + $mos.data.Count)
  $first = @($mos.data | Where-Object { $_.status -eq "requested" } | Select-Object -First 1)
  if ($first -and $first.id) {
    $st = Invoke-RestMethod -Uri "$api/v1/material-orders/$($first.id)/status?status=confirmed" -Method POST -Headers $u.h
    Note "supplier" "confirm material order" ($st.data.status -eq "confirmed") $st.data.status
  } else { Note "supplier" "confirm material order" $true "none requested" }
} catch { Note "supplier" "flow" $false $_.Exception.Message }

foreach ($pair in @(
    @("lawyer@demo.superapp", "lawyer"),
    @("excavator@demo.superapp", "excavator"),
    @("admin@demo.superapp", "admin")
  )) {
  try {
    $x = Login $pair[0]
    Note $pair[1] "login JWT" ($null -ne $x.token) $x.user.role
    $me = GetJson "$api/v1/auth/me" $x.h
    Note $pair[1] "GET /me" ($me.data.email -eq $pair[0])
  } catch { Note $pair[1] "login" $false $_.Exception.Message }
}

try {
  $em = "demo" + (Get-Random -Maximum 99999) + "@test.kz"
  $regBody = '{"email":"' + $em + '","password":"secret1","full_name":"Demo New","phone":"+7701","role":"buyer"}'
  $reg = Invoke-RestMethod -Uri "$api/v1/auth/register" -Method POST -ContentType "application/json" -Body $regBody
  Note "register" $em ($null -ne $reg.data.token)
} catch { Note "register" "new buyer" $false $_.Exception.Message }

Write-Output ""
Write-Output ("TOTAL PASS={0} FAIL={1}" -f $ok, $fail)
if ($fail -gt 0) { exit 1 } else { exit 0 }
