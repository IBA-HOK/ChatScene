# Archer (2005) / Cooper & Ferguson (1976) — 日本語訳（指定箇所：DRAC・PSD整理、閾値根拠。2冊で1セット）

書誌情報:
- Archer, J. (2005). Indicators for traffic safety assessment and prediction and their application in micro-simulation modelling: A study of urban and suburban intersections. Doctoral Thesis, KTH, Stockholm. TRITA-INFRA 2005:013.
- Cooper, D.F. and Ferguson, N. (1976). Traffic studies at T-junctions. 2. A conflict simulation model. Traffic Engineering & Control, 17(7), 306-309. [原文閉鎖。TRID Accession No. 00148046。以下はArcherによる整理の訳]
原文ファイル: ../Archer2005_Thesis.pdf
訳出範囲: Archer Ch.5（DR / DST / PSD 定義、Table 5.3、RBR）、Ch.9（serious/non-serious閾値 -3.35→-2.00 m/s^2）

---

## 5.3.5 Alternative representations of conflict severity（葛藤重大度の代替表現）

事故の実際の結果重大度は、衝突物の衝撃力に直接関係し、これはニュートンの第3基本法則に従い加速度と質量の変化（すなわち運動量）に比例して定義される。したがって、事故近接水準が「近い」が速度が相対的に低い葛藤状況は、高い事故リスク水準を示すが人的傷害リスクは低いことを示しうる。一般に、高速は傷害・死亡リスクと関係する（すなわち速度は事故結果重大度のよい指標である）。この理由から、重大度の適切な水準を確立するためには速度の値、またはより好ましくは加速度の値を用いることが有用である。

## Deceleration Rate (DR)（減速度）

この測度は、衝突を避けるために車両が減速しなければならない最高率の測度にほかならない（FHWA, 2003）。減速力はHydén（1987）により葛藤の重大度決定の重要側面として言及されている。MinderhoudとBovy（2001）が示唆した拡張TTC測度と同様に、特定減速度閾値（例：-2.0 m/s^2）の下で費やした時間を測定すること、および積分は理論的に可能である。しかし例えば写真測量解析を用いた実際減速度の測定は困難で資源集約的である。

## Deceleration-to-Safety Time (DST)（安全までの減速）

上記と同様に、この指標は、PETが0秒を超える値に達するのに必要な減速度（ここではこれが主要回避行動である）として定義される。この測度は、交通葛藤技法およびPETで用いられるTA測度の補完として、車両と歩行者の相互作用における安全水準を決定するために写真測量解析と併せて用いられてきた（Topp, 1998）。

## Proportion of Stopping Distance (PSD)（停止距離比）

この測度は、予測衝突点までの必要な制動距離に対する、操縦に利用可能な距離の比を表す（FHWA, 2003）。

## Table 5.3 Deceleration-to-Safety braking levels proposed by Hydén (1996)（Hydén (1996) が提案したDST制動水準）

| 葛藤水準 | Deceleration-to-Safety | 記述 |
|---|---|---|
| 葛藤なし | 制動率 <= 0 m/s^2 | 回避行動不要 |
| 葛藤なし | 制動率 0〜-1 m/s^2 | 適応必要 |
| 1 | 制動率 -1〜-2 m/s^2 | 反応必要 |
| 2 | 制動率 -2〜-4 m/s^2 | かなりの反応必要 |
| 3 | 制動率 -4〜-6 m/s^2 | 強い反応必要 |
| 4 | 制動率 < -6.00 m/s^2 | 緊急反応必要 |

## Required Braking Rate (RBR)（所要制動率）

本論文の目的のためには、所要減速度（RBR）が事故重大度リスクのより適切な予測子であり、ほとんどの近接安全指標測度に適用できるものと考える。

## 9. Case Study 3（serious/non-serious閾値）

serious（およびnon-serious）葛藤の生成に関して、安全臨界事象のシミュレーションは多くの困難を浮き彫りにした。serious葛藤の数は、各時間帯シナリオに関する頻度と合計所要制動率重大度水準の両方に関して、一貫して大幅に過小評価された。seriousとnon-serious葛藤を区別する閾値関数を実験的に引き下げること（約-3.35から-2.00 m/s^2へ）により、シミュレーションと観測の頻度・重大度データ間の高い相関が得られた。

## Cooper & Ferguson (1976) 原典情報（訳出ではなく書誌特定）

- Cooper, D.F., Ferguson, N. (1976). Traffic studies at T-junctions. 2. A conflict simulation record. Traffic Engineering & Control, 17(7), 306-309.
- 内容（TRID抄録による）: T字路における事故リスク評価のためのシミュレーションモデル。交通葛藤の概念に基づく。個々の車両の動きを監視するイベント・ステッピング・シミュレーションプログラムにより実装。事象と車両相互作用を定義し、運転者の転回決定が葛藤の発生に至ることを示す。
- 原文PDFは公開なし。本訳ではArcher (2005) の上記整理をもって2冊1セットの訳とする。
