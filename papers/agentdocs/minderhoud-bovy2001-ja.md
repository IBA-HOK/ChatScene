# Minderhoud & Bovy. Extended time-to-collision measures for road traffic safety assessment (2001) — 日本語訳（指定箇所）

書誌情報: Minderhoud, M.M. and Bovy, P.H.L. (2001). Extended time-to-collision measures for road traffic safety assessment. Accident Analysis & Prevention, 33(1), 89-97.
原文ファイル: ../MinderhoudBovy2001_TTC.pdf
訳出範囲: Abstract / 2. Time-to-collision notion（2.1 定義・式(1)、2.2 臨界値、2.3 接近法） / 4. Definition of two TTC-based indicators（4.1 TET・式(2)(3)、4.2 TIT・式(4)(5)(6)）

---

## Abstract（要旨）

本論文は、比較道路交通安全解析に適した、time-to-collisionの概念に基づく2つの新しい安全指標を記述する。このような安全指標は、何もしない場合と、例えば知能運転者支援システムの導入のような適合状況との比較に適用できる。断面で測定される古典的time-to-collision値とは対照的に、改良された安全指標は、特定の道路区間について特定の時間 horizon にわたり収集された車両軌跡を用いて、全体的安全指標値を計算する。車両固有の指標値だけでなく、安全臨界確率も、開発された安全測度から容易に決定できる。導出された安全指標の適用は、運転者支援システムの潜在的安全影響の評価のために例示される。それによれば、一部の自律型知的クルーズコントロール（AICC）設計は、支援なしの参照場合よりも安全臨界的であることが分かる。安全評価に適用する指標閾値は、安全特性を持つ先進AICCシステムが導入されるときには適合させなければならないことが示唆される。

## 2. Time-to-collision notion（time-to-collisionの概念）

### 2.1 Definition（定義）

time-to-collision概念は1971年に米国の研究者Haywardにより導入された。時点tにおけるTTC値は、衝突進路と速度差が維持されたとした場合に2車両間の衝突までに残された時間として定義される。

先行車両 i-1 に対する車両・運転者結合 i の時点tにおけるtime-to-collisionは、次式で計算できる。

```
Xi-1(t) - Xi(t) - li
TTC_i = ─────────────────────  (1)
        Ẋi(t) - Ẋi-1(t)
```

ここで Ẋ は速度、X は位置、l は車両長を表す。

TTC値を計算するためには、時点tにおける速度差が、時点t'までの車両の仮想衝突軌跡の間、一定に保たれると仮定する。TTC値が高いほど状況は安全である。

### 2.2 Critical time-to-collision value（臨界time-to-collision値）

安全臨界接近状況は小さなTTC値で特徴づけられる。HirstとGraham（1997）は、運転者が意図せず危険状況に陥る場合と、運転者が制御を維持している場合を区別するために4秒のtime-to-collision測度を用いることができると報告している。当該研究はさらに、衝突警告システムの設計の実験室実験を記述する。結果は、4秒または5秒のTTC警告基準は誤警報が多すぎることを示す。当該研究は、3秒のTTC値が最小の警報数を生じたが、一部の場合には臨界状況が観測されたことを示す。HogemaとJanssen（1996）は、運転シミュレータ実験における、支援なしと支援あり運転者に対するキューへの接近時の運転者行動を研究した。支援なし運転者に対しては最小3.5秒、支援あり運転者に対しては2.6秒の最小TTC値が見出された。2.6秒値は安全上の懸念とみなされる。VanDerHorst（1990）は、交差点への接近に基づき、さらに低い臨界TTC値を報告している。

### 2.3 Approaches for determining time-to-collision values（time-to-collision値決定の接近法）

文献ではTTC値を安全評価のために決定する2つの接近法が基本的に観察される。一方は道路断面を通過する車両のtime-to-collision値に着目する。この方法は経験的交通流研究や微視的シミュレーション研究で主に用いられる。他方は、実交通または運転シミュレータにおける被験運転者が、一定期間運転する、または特定経路を追従することに着目する。被験者の運転成績（time-to-collisionを含む）は継続的に測定され、その後、最小time-to-collision値が決定できる。

われわれの提案は2つの接近法を結合し、2つの新しい安全指標（TETとTITと呼ぶ）とする。単一断面の代わりに特定道路延長を安全解析のために考慮する。この接近法では、すべての交通参加者の小さなtime-to-collision値の発生を、任意の時点で考慮できる。

## 4. Definition of two TTC-based road traffic safety indicators（2つのTTC基礎道路交通安全指標の定義）

X1からX2までの道路区間を考える。道路区間長をL、時間帯T1からT2までの継続時間をHで表す。各車両iについて時間に対するtime-to-collisionプロファイル TTC_i(t) を式(1)を用いて決定できる。TTC閾値 TTC* は、安全な接近と安全臨界接近を区別するために適用できるtime-to-collision値である。

### 4.1 The TET indicator（TET指標）

最初に規定する指標はTETと呼ばれ、Time Exposed Time-to-collisionを表す。特定時間継続 H に対する安全臨界time-to-collision値への曝露継続時間が安全指標として用いられる。これは、閾値 TTC* を下回るTTC値で前方車両に接近するすべての時点（考慮時間帯にわたる）の合計である。後者は安全接近と安全臨界接近の境界とみなされる。したがってTET値が低いほど（時間帯Hにおける平均では）状況は安全である。

```
       T
TET*_i = Σ δ_i(t)・t_sc   (2)
       t=0

δ_i(t) = 1  0 < TTC_i(t) < TTC* の場合
         0  その他
```

t_sc は小時間刻み（例：0.1秒）である。N台の運転者（i=1…N）に対する全TET*は次に等しい。

```
        N
TET* = Σ TET*_i   (3)
       i=1
```

TET指標は秒で表される。上付き*は「閾値に対する指標値」と解釈すべきである。

### 4.2 The TIT indicator（TIT指標）

TET指標の1つの欠点は、閾値を下回る場合のTTC値がTET指標値に影響しないことである。しかし理論によれば、きわめて小さいTTC値（例：0.5秒未満）は、より高いTTC値（例：2秒または3秒）に比べて衝突の相対的に高い確率を持つ接近状況を表すことが予想される。安全評価においてTTC値の影響を考慮するため、TIT指標が開発された。

TIT（Time Integrated Time-to-collision）指標は、運転者のtime-to-collisionプロファイルの積分を用いて安全水準を表す（単位 s^2）。連続時間では：

```
      N   T
TIT* = Σ ∫ [TTC* - TTC_i(t)] dt   0 < TTC_i(t) < TTC* の場合  (4)
      i=1 0
```

個別被験者 i の離散時間における個別TITは次式で計算できる。

```
       T
TIT*_i = Σ [TTC* - TTC_i(t)]・t_sc   0 < TTC_i(t) < TTC* の場合  (5)
       t=0
```

時間帯H中に調査に存在した全車両（i=1…N）に対する合計は、次の離散時間集計TIT定義となる（s^2で表す）。

```
       N
TIT* = Σ TIT*_i   (6)
      i=1
```

高いTIT値は、継続時間重み付き不安全TTC値への大きな曝露時間を意味し、道路安全にとっては負である。
