# Graph sources, parameter rubric and limits

`nodes.yaml` and `edges.yaml` are a small, hand-curated **scenario model**, not a dataset. This
file says what evidence stands behind each edge and, separately, which numbers are analyst
judgement. Every edge has a line below in the form `source->target: citation`
(`tests/unit/test_graph_seed_corridors.py` checks that no edge lacks one and none is stale).

Vocabulary used in the citations:

* **derived** — the weight is computed from a cited figure; the calculation is in "Worked derivations".
* **modeled** — an analyst estimate placed in a rubric band; the cited context anchors it but does not determine it.
* **structural link** — the connection is uncontroversial, but no dataset backs its strength.

## Edge citations

### Corridor 1 — North Sea (pre-existing)

Dataset-level pointers written with the original graph. They name a statistical source and a
year but do not record how each weight was derived, so treat those weights as modeled too.

port_hamburg->route_north_sea: Eurostat maritime freight statistics 2023, Hamburg North Sea flows
port_rotterdam->route_north_sea: Eurostat maritime freight statistics 2023, Rotterdam North Sea flows
port_antwerp->route_north_sea: Eurostat maritime freight statistics 2023, Antwerp North Sea flows
route_north_sea->com_auto_parts: Eurostat 2023 maritime freight, North Sea automotive goods
route_north_sea->com_chemicals: Eurostat 2023 maritime freight, North Sea chemical goods
route_north_sea->com_containers: Port of Rotterdam throughput report 2023, container volumes
port_hamburg->com_auto_parts: Eurostat 2023 maritime freight, DE auto components
port_rotterdam->com_auto_parts: Eurostat 2023 maritime freight, NL auto components
port_antwerp->com_auto_parts: Eurostat 2023 maritime freight, BE auto components
port_hamburg->com_chemicals: Eurostat 2023 maritime freight, DE chemical products
port_rotterdam->com_chemicals: Eurostat 2023 maritime freight, NL chemical products
port_antwerp->com_chemicals: Eurostat 2023 maritime freight, BE chemical products
route_north_sea->route_rhine: CCNR annual inland navigation market observation 2023
com_auto_parts->ind_auto_parts_de: Destatis automotive production and input table 2022
com_auto_parts->ind_auto_parts_pl: GUS Poland industrial input-output table 2022
com_auto_parts->ind_auto_parts_cz: Czech Statistical Office automotive industry table 2022
com_chemicals->ind_chemicals_de: Destatis chemical manufacturing input table 2022
com_containers->ind_logistics_cee: Eurostat road freight transport by region 2023
route_rhine->ind_logistics_cee: CCNR Rhine freight performance report 2023
ind_auto_parts_de->mkt_germany: Destatis motor vehicle production 2023
ind_auto_parts_de->mkt_cee_retail: Eurostat intra-EU automotive goods trade, Germany to CEE 2023
ind_auto_parts_pl->mkt_poland: GUS manufacturing output 2023
ind_auto_parts_cz->mkt_czechia: Czech Statistical Office manufacturing output 2023
ind_chemicals_de->mkt_germany: Destatis chemical products output 2023
ind_logistics_cee->mkt_poland: Eurostat regional road freight Poland 2023
ind_logistics_cee->mkt_czechia: Eurostat regional road freight Czechia 2023
ind_logistics_cee->mkt_cee_retail: Eurostat wholesale and retail trade region data 2023
mkt_germany->mkt_cee_retail: Eurostat intra-EU trade by destination 2023
mkt_poland->mkt_ukraine_aftermarket: UN Comtrade 2023 Poland-UA automotive parts trade
mkt_cee_retail->mkt_ukraine_aftermarket: UN Comtrade 2023 EU-UA vehicle parts trade
mkt_czechia->mkt_ukraine_aftermarket: UN Comtrade 2023 Czechia-UA vehicle parts trade
mkt_poland->mkt_baltic: UN Comtrade 2023 Poland-Baltic automotive parts trade
mkt_poland->mkt_balkans: UN Comtrade 2023 Poland-Balkans parts trade
mkt_czechia->mkt_balkans: UN Comtrade 2023 Czechia-Balkans parts trade
com_auto_parts->mkt_ukraine_aftermarket: UN Comtrade 2023 EU-UA automotive components trade

### Corridor 2 — Suez / Red Sea (Asia–Europe electronics and machinery)

chokepoint_red_sea->chokepoint_suez: IMF-2024: Red Sea attacks reduced Suez traffic (trade volume -50% y/y, Jan-Feb 2024); UNCTAD-2024: Suez transits -55% y/y by mid-Oct 2024. Weight modeled: Asia-Europe Suez traffic passes Bab el-Mandeb
chokepoint_red_sea->com_electronics: EUROSTAT-CN + EUROSTAT-MODE-2023: electrical equipment is a top-2 EU import group from China; sea = 51.0% of 2023 extra-EU import value. Weight modeled (sea x Asia x Suez share)
chokepoint_red_sea->com_semiconductors: EUROSTAT-MODE-2023: air = 17.4% of 2023 import value but 0.2% of tonnage (high unit value), so chips skew to air. Weight modeled, deliberately low
chokepoint_red_sea->com_machinery: EUROSTAT-CN: machinery and mechanical parts is a top-2 EU import group from China; EUROSTAT-MODE-2023: sea = 74.0% of import tonnage. Weight modeled
chokepoint_red_sea->com_containers: UNCTAD-2024: rerouting away from the Red Sea and Panama Canal raised container-ship demand 12% by mid-2024. Weight modeled
chokepoint_red_sea->port_piraeus: COSCO-2023: Piraeus Container Terminal handled 4,586.5k TEU in 2023. Weight modeled (Asia-Europe services calling Piraeus route via Suez)
chokepoint_suez->com_electronics: IMF-2024: Suez carries about 15% of global maritime trade; EUROSTAT-CN + EUROSTAT-MODE-2023 as for the Red Sea edge. Weight modeled
chokepoint_suez->com_semiconductors: EUROSTAT-MODE-2023: air = 17.4% of 2023 import value but 0.2% of tonnage (high unit value). Weight modeled, deliberately low
chokepoint_suez->com_machinery: EUROSTAT-CN + EUROSTAT-MODE-2023: machinery is a top-2 import group and sea carries 74.0% of import tonnage. Weight modeled
chokepoint_suez->com_containers: UNCTAD-2024: container-ship demand +12% from Red Sea and Panama rerouting; IMF-2024: Cape rerouting added 10+ days to delivery. Weight modeled
chokepoint_suez->port_piraeus: COSCO-2023: Piraeus Container Terminal handled 4,586.5k TEU in 2023. Weight modeled (Asia-Europe services calling Piraeus route via Suez)
route_cape_good_hope->com_electronics: IMF-2024: Cape volume +74% (Jan-Feb 2024), delivery +10 days; UNCTAD-2024: Cape rerouting capacity +89%. Weight modeled (alternative-route share)
route_cape_good_hope->com_machinery: IMF-2024 + UNCTAD-2024: as for the electronics edge. Weight modeled
port_piraeus->mkt_seeurope_imports: SASAC-2024: Piraeus is the largest port in Greece. Weight modeled
port_piraeus->route_land_sea_express: SASAC-2024: Land-Sea Express uses Piraeus as its key node (30+ trains a week, 180,000+ TEU in 2022; operator-reported). Weight modeled
route_land_sea_express->ind_logistics_cee: SASAC-2024 vs COSCO-2023: the line carried 180,000 TEU in 2022 against 4,352.1k TEU at Piraeus Container Terminal (~4%), a niche channel. Weight modeled, marginal band
route_land_sea_express->mkt_cee_retail: SASAC-2024: containers move by rail from Piraeus to Prague and other inland stations (niche channel, see the logistics edge). Weight modeled, marginal band
com_electronics->ind_electronics_eu: EUROSTAT-CN: electrical equipment is a top-2 EU import group from China. Weight modeled (structural link, no dataset)
com_electronics->mkt_eu_retail: EUROSTAT-CN: electrical equipment is a top-2 EU import group from China. Weight modeled (structural link, no dataset)
com_semiconductors->ind_electronics_eu: EC-CHIPS: the chip shortage disrupted supply chains. Weight modeled (structural link, no dataset)
com_semiconductors->ind_auto_parts_de: EC-CHIPS: the chip shortage caused product shortages ranging from cars to medical devices. Weight modeled
com_machinery->ind_machinery_eu: EUROSTAT-CN: machinery and mechanical parts is a top-2 EU import group from China. Weight modeled (structural link, no dataset)
ind_electronics_eu->mkt_eu_retail: Structural link. Weight modeled (analyst estimate, no dataset)
ind_electronics_eu->mkt_germany: Structural link. Weight modeled (analyst estimate, no dataset)
ind_machinery_eu->mkt_germany: Structural link. Weight modeled (analyst estimate, no dataset)
ind_machinery_eu->mkt_poland: Structural link. Weight modeled (analyst estimate, no dataset)
ind_machinery_eu->mkt_czechia: Structural link. Weight modeled (analyst estimate, no dataset)
mkt_eu_retail->mkt_cee_retail: Structural link. Weight modeled (analyst estimate, no dataset)

### Corridor 3 — Black Sea grain (Odesa / Constanta / Bosphorus to MENA food markets)

route_black_sea->chokepoint_bosphorus: MONTREUX-1936: passage through the Turkish Straits is governed by the 1936 Convention; they are the Black Sea's only sea outlet (geography). Weight modeled
route_black_sea->com_grain: USDA-2023: 96% of Ukrainian grain and oilseed exports were seaborne in 2021. Weight modeled (all seaborne Black Sea exports)
route_black_sea->port_odesa: USDA-2023: Russia blocked all Ukrainian deep-sea ports from Mar to Jul 2022. Weight modeled
route_black_sea->port_constanta: USDA-2023: Constanza (Romania) was part of the diverted export route via the Danube. Weight modeled
chokepoint_bosphorus->com_grain: UN-JCC: Black Sea Grain Initiative vessels proceeded towards Istanbul along the humanitarian corridor; MONTREUX-1936 (geography). Weight modeled (excludes intra-Black-Sea destinations)
port_odesa->com_grain: FAO-2023: Russia 15% + Ukraine 10% of 2021 world wheat exports (Ukraine = 10/25 = 40% of the pair); USDA-2023: 96% of Ukrainian exports seaborne. Weight derived, rounded
port_constanta->com_grain: USDA-2023 + EC-SOLIDARITY-2024: alternative routes via Constanza handled only a fraction of exports; the EC group facilitated Constanta traffic management. Weight modeled
route_danube->port_constanta: USDA-2023: diverted flow moved via Izmail and Reni (Ukraine) and Constanza (Romania). Weight modeled
route_danube->com_grain: USDA-2023: Danube ports carried only a fraction of exports seeking routes. Weight modeled, low
route_solidarity_lanes->com_grain: USDA-2023: the seaborne share fell from >96% (2021) to ~69% (2022), so ~31% moved by other routes. Weight derived
port_odesa->ind_agri_ua: USDA-2023: 96% of Ukrainian grain exports seaborne (2021); transport costs more than doubled in 2022. Weight modeled
port_constanta->ind_agri_ua: USDA-2023 + EC-SOLIDARITY-2024: Constanta is part of the alternative export corridor. Weight modeled
com_grain->mkt_egypt_wheat: FAO-2023 figs 26-27: Egypt sourced 78% (2021) and 66% (2022) of wheat imports from Russia and Ukraine. Weight derived = mean 0.72
com_grain->ind_milling_tr: FAO-2023 figs 26-27: Turkiye sourced 88% (2021) and 94% (2022) of wheat imports from Russia and Ukraine. Weight derived = mean 0.91
com_grain->mkt_mena_food: FAO-2023 fig 15: many North Africa and Western/Central Asia countries imported the majority of their 2021 wheat from Russia and Ukraine. Weight modeled (>0.5)
com_grain->mkt_global_food: FAO-2023: Russia and Ukraine about 26% of 2021 world wheat exports; FAO Food Price Index fell 22% Mar 2022-May 2023, in part reflecting the Black Sea Grain Initiative and Solidarity Lanes. Weight modeled
ind_milling_tr->mkt_mena_food: FAO-2023: Turkiye exports wheat flour to Yemen, Somalia, Iraq and others. Weight modeled
mkt_egypt_wheat->mkt_mena_food: FAO-2023: Egypt imported over 11 million tonnes of wheat in 2021. Weight modeled

## References

Read 2026-09-21. **Fetched** means the origin document was downloaded and the quoted statement
located in its text. IMF and UNCTAD block automated fetches, so those two were read through
Internet Archive copies of the same URLs.

- **IMF-2024** — IMF Blog, "Red Sea Attacks Disrupt Global Trade", 7 March 2024. <https://www.imf.org/en/blogs/articles/2024/03/07/red-sea-attacks-disrupt-global-trade>. Used: Suez normally carries about 15 percent of global maritime trade volume; Suez trade volume fell 50 percent year on year in the first two months of 2024; trade around the Cape of Good Hope rose an estimated 74 percent; rerouting "increased delivery times by 10 days or more on average".
- **UNCTAD-2024** — UNCTAD, "Suez and Panama Canal disruptions threaten global trade and development", 22 October 2024. <https://unctad.org/news/suez-and-panama-canal-disruptions-threaten-global-trade-and-development>. Used: by mid-October 2024 Suez transits averaged 33 a day, 57% below the previous peak and 55% below a year earlier; rerouting capacity around the Cape rose 89%; by mid-2024 rerouting away from the Red Sea and Panama Canal raised container-ship demand by 12%.
- **COSCO-2023** — COSCO SHIPPING Ports Ltd, "Container Throughput 2023" (monthly terminal table, PDF). <https://ports.coscoshipping.com/en/Businesses/MonthlyThroughput/pdf/2023.pdf>. Used: Piraeus Container Terminal S.A. handled 4,586.5 thousand TEU in 2023 and 4,352.1 thousand in 2022 (December year to date, +5.4%). Fetched. Covers COSCO's Piraeus terminals only, not every terminal in the port.
- **SASAC-2024** — China SASAC / COSCO SHIPPING, "Rapid Development of the China-Europe Land-Sea Express Line: Creating an Efficient Logistics Corridor", 23 May 2024. <http://en.sasac.gov.cn/2024/05/23/c_17219.htm>. Used: Piraeus is the largest port in Greece; the line runs 10+ routes to nine inland European stations with 30+ trains a week; it carried over 180,000 TEU on 2,600+ train trips in 2022. Fetched. Operator-reported by a state-owned company, i.e. an interested source.
- **EUROSTAT-MODE-2023** — Eurostat, Statistics Explained, "International trade in goods by mode of transport" (data extracted June 2024). <https://ec.europa.eu/eurostat/statistics-explained/index.php/International_trade_in_goods_by_mode_of_transport>. Used: in 2023 sea carried 51.0% of extra-EU import value and 74.0% of import tonnage; air carried 17.4% of import value but just 0.2% of tonnage, which Eurostat reads as "the high unit value of goods transported by air". Fetched (static PDF rendering of the article).
- **EUROSTAT-CN** — Eurostat, Statistics Explained, "EU trade with China - latest developments". <https://ec.europa.eu/eurostat/statistics-explained/index.php?title=China-EU_-_international_trade_in_goods_statistics>. Used: electrical equipment, and machinery and mechanical parts, are the top-2 product groups imported from China. Fetched. A rolling page (viewed September 2026), so the ranking may move; used qualitatively only.
- **EC-CHIPS** — European Commission, "European Chips Act", Shaping Europe's digital future. <https://digital-strategy.ec.europa.eu/en/policies/european-chips-act>. Used: "The recent global chips shortage has disrupted supply chains, caused product shortages ranging from cars to medical devices, and in some cases even forced factories to close." Fetched.
- **FAO-2023** — FAO, Information Note, "The importance of Ukraine and the Russian Federation for global agricultural markets and the risks associated with the war in Ukraine", 3 July 2023 update. <https://openknowledge.fao.org/server/api/core/bitstreams/4fce6098-a3ba-4742-b8f4-685454a5d409/content>. Used: 2021 wheat exports, Russia 32.9 Mt = 15% of global shipments and Ukraine 20 Mt = 10% (about 26% together, about 17% in 2022); Figure 26 (2021) and Figure 27 (2022), share of wheat imports from Russia and Ukraine: Egypt 78% and 66%, Turkiye 88% and 94%; Egypt imports over 11 Mt of wheat; many North African and Western/Central Asian importers took the majority of their wheat from the two (Fig. 15); Turkiye mills imported wheat and exports flour to Yemen, Somalia, Iraq and others; the FAO Food Price Index fell 22% between March 2022 and May 2023, in part reflecting the Black Sea Grain Initiative and EU Solidarity Lanes. Fetched.
- **USDA-2023** — USDA Agricultural Marketing Service, "Ukraine Grain Transportation", June 2023. <https://www.ams.usda.gov/sites/default/files/media/UkraineJune2023.pdf>. Used: the share of Ukrainian grain exports shipped via Black Sea ports fell from 96% (2021) to 69% (2022); Russia blocked all Ukrainian deep-sea ports from March to July 2022; diversion via rail and the Danube ports Izmail and Reni (Ukraine) and Constanza (Romania) handled "only a fraction" of the exports seeking routes; Ukrainian transport costs more than doubled. Fetched.
- **EC-SOLIDARITY-2024** — European Commission (DG MOVE), "Solidarity Lanes: improving the Danube routes together", 17 May 2024. <https://transport.ec.europa.eu/news-events/news/solidarity-lanes-improving-danube-routes-together-2024-05-17_en>. Used: the group facilitated traffic management at the entrance to Constanta port and "brought millions of tons of agricultural exports to global markets". Fetched.
- **UN-JCC** — United Nations, Black Sea Grain Initiative / Joint Coordination Centre. <https://www.un.org/en/black-sea-grain-initiative>. Used: vessels "proceed towards Istanbul along the agreed maritime humanitarian corridor". Fetched.
- **MONTREUX-1936** — Convention Regarding the Regime of the Straits, signed at Montreux on 20 July 1936. Used only for the geographic and legal fact that passage through the Turkish Straits, the Black Sea's only sea outlet, is governed by this treaty. **Not fetched** this session and cited from general knowledge; no figure depends on it.

## Parameter rubric

* **criticality** (node, 0-1) — systemic importance. Used only when the node is an epicentre: initial impact = severity/5 x criticality. 0.90-0.95 chokepoints carrying about 15% of global maritime trade (Suez, IMF-2024) and the largest gateways; 0.75-0.89 sole-outlet chokepoints, leading export ports and strategic commodities; 0.50-0.74 regional hubs, industries and markets; below 0.50 auxiliary routes.
* **resilience** (node, 0-1) — ability to absorb an incoming shock; it multiplies incoming impact by (1 - resilience). 0.10-0.20 no bypass or war-exposed (Odesa, the straits); 0.25-0.35 partial bypass; 0.40-0.50 diversified or buffered.
* **weight** (edge, 0-1) — modeled share of the target's flow or inputs that depends on the source. 0.80-0.95 structural, no bypass; 0.50-0.79 majority dependence; 0.25-0.49 significant minority; 0.10-0.24 marginal or niche.
* **lead_time_days** (edge) — days before the disruption is felt downstream: sailing time between the nodes plus typical inventory buffers. Modeled.
* **substitutes** (node) — used sparingly, because the simulator halves incoming impact while any listed substitute is unaffected. Only `com_electronics` and `com_machinery` list one (`route_cape_good_hope`, a documented and heavily used alternative: IMF-2024, UNCTAD-2024). Grain lists none: no alternative to the Turkish Straits exists for seaborne Black Sea exports and USDA-2023 reports that the alternative routes carried only a fraction, so that partial alternative is modeled as the `route_solidarity_lanes` and `route_danube` edges instead. Semiconductors list none: the air-freight alternative is reflected in their low edge weights and higher resilience.
* **edge type** — `transits` (a flow passes through the source), `handles` (the source processes the commodity), `supplies` (the source feeds the target), `depends_on` (the target's activity relies on the source).

## Worked derivations

| Edge | Calculation | Weight |
|---|---|---|
| `port_odesa->com_grain` | Ukraine 10% / (Russia 15% + Ukraine 10%) = 0.40 (FAO-2023); 96% seaborne (USDA-2023) barely moves it | 0.40 |
| `com_grain->mkt_egypt_wheat` | mean(78% in 2021, 66% in 2022) = 0.72 (FAO-2023 figs 26-27) | 0.72 |
| `com_grain->ind_milling_tr` | mean(88% in 2021, 94% in 2022) = 0.91 (FAO-2023 figs 26-27) | 0.91 |
| `route_solidarity_lanes->com_grain` | 1 - 69% seaborne share in 2022 = 0.31 (USDA-2023), rounded | 0.30 |
| `route_land_sea_express->ind_logistics_cee` | 180,000 TEU by rail / 4,352,100 TEU at Piraeus Container Terminal in 2022 = 4.1% (SASAC-2024, COSCO-2023): a niche channel, so marginal band | 0.15 |

Calibration check: for a severity-4 Red Sea event the model gives Suez an impact of 0.39; the IMF
observed a 50% fall in Suez volume during the actual Red Sea campaign. Same order of magnitude,
not a fit.

## Limits — read before quoting a number

1. **The weights are modeled, not measured.** Only the rows above are computed from a cited figure. Everything else is a judgement placed in a rubric band and anchored by context. No weight was fitted to historical disruptions (backtesting is in the project backlog).
2. **The simulator compounds decay.** Each hop multiplies by `decay^(hops+1)` on an impact that is already attenuated, so impact falls roughly as `decay^(1+2+...+k)`. With the default 0.75, cascades rarely pass two hops (the North Sea corridor behaves the same: Hamburg at severity 5 reaches 7 nodes, maximum 2 hops). Read `impact_score` as a relative ranking, not a probability. Raising the `decay` request parameter to 1.0 lifts the scores and widens the cascade (Suez at severity 5: 10 to 12 impacted nodes) but the maximum depth stays at 2 hops, because the weights and the 0.02 pruning threshold cap it too.
3. **Evidence anchors the corridors, not every edge.** Downstream "structural link" edges (industry to market) have no dataset behind their strength.
4. **Source quality varies.** SASAC-2024 is operator-reported; EUROSTAT-CN is a rolling page; COSCO-2023 covers COSCO's terminals only; MONTREUX-1936 was not fetched.
5. **No product-level mode split exists here for semiconductors.** Their low weights rest on Eurostat's all-goods value-versus-tonnage contrast (air: 17.4% of value, 0.2% of tonnage), not on chip-specific data.

## Follow-ups for Person 2 (`agent/aliases.yaml` is theirs; not edited here)

* New graph ids with no alias yet, so a headline naming them resolves to `None` and the simulation returns nothing: `route_black_sea` ("Black Sea"), `route_cape_good_hope` ("Cape of Good Hope"), `route_danube` ("Danube"), `route_solidarity_lanes` ("Solidarity Lanes"), `route_land_sea_express` ("Land-Sea Express"), `com_machinery` ("machinery").
* **Existing id mismatch:** `aliases.yaml` maps "German automotive industry" to `ind_auto_de`, but the graph node is `ind_auto_parts_de`. `simulate()` silently ignores unknown ids, so that headline currently produces an empty cascade.

## TODO - corridor 4 (semiconductors / energy), explicitly out of scope for this stage

Alias ids that still have no graph node. They are recorded here and pinned in `KNOWN_GAPS` in the
test, not silently dropped: `port_gdansk`, `port_koper`, `chokepoint_hormuz`, `chokepoint_panama`,
`chokepoint_malacca`, `com_steel`, `com_crude_oil`, `com_lng`.
