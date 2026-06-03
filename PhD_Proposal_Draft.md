# PhD Research Proposal

**Programme:** MaMTEP — Macroeconomics and Theory of Economic Policy
**Institution:** Aalborg University, Department of Economics and Politics
**Supervisory alignment:** Post-Keynesian Political Economy, Ecological Macroeconomics

---

## Title

**Municipal Fiscal Resilience in the Green Transition: A Stock-Flow Consistent Analysis of Climate Exposure Heterogeneity across Danish Local Governments**

---

## Abstract

Denmark's green transition will impose structurally uneven fiscal costs across its 98 municipalities. Localities with high fossil-sector employment, limited renewable capacity, and stretched balance sheets face compounded vulnerabilities — simultaneously losing tax base, incurring transition costs, and confronting rising physical climate risks — while possessing fewer fiscal buffers than their low-exposure counterparts. Yet existing macroeconomic frameworks treat this heterogeneity as a second-order concern: aggregate SFC models assume representative-agent local governments, and standard municipal finance analysis lacks the theoretical structure to trace how transition shocks propagate through sectoral accounts.

This thesis develops an integrated research infrastructure that combines Stock-Flow Consistent (SFC) macroeconomic modelling with granular municipal-level data to analyse fiscal resilience under alternative green transition policy scenarios. Drawing on Statistics Denmark's open data infrastructure, energy and climate indicators from Energistyrelsen and DMI, and NACE-level employment microdata, I construct a transition vulnerability index for all 98 Danish municipalities and calibrate a two-sector SFC model to contrasting archetype municipalities. Three papers examine: (1) the empirical structure of climate-fiscal exposure heterogeneity; (2) the SFC dynamics of fiscal resilience under alternative transition trajectories; and (3) the design of policy instruments that minimise fiscal stress in high-exposure municipalities within a coherent macroeconomic framework.

The proposal is grounded in a functional research prototype — AreaStat DK — which demonstrates the data infrastructure, SFC account structures, and scenario visualisations underpinning the empirical work.

---

## 1. Motivation and Research Gap

### 1.1 The Green Transition as a Fiscal Problem

The political economy of the green transition is typically framed at the national level: carbon pricing, green investment packages, industrial policy. But the distributional incidence of transition costs and benefits is fundamentally local. In Denmark, municipalities bear legal responsibility for key green transition expenditures — building retrofits, local mobility, heat planning, waste — and simultaneously collect the income and property tax revenues that will be directly affected by sectoral restructuring.

When fossil-linked industries contract — oil services, transport logistics, conventional agriculture — the municipalities hosting them face a compound shock: employment falls, the local income-tax base erodes, equalization grant entitlements shift, and capital expenditure needs for green infrastructure rise simultaneously. This is precisely the configuration that Minsky's (1986) financial instability hypothesis identifies as generating balance-sheet fragility: a simultaneous deterioration of flows (income) and stocks (debt/asset ratios), with limited capacity for self-correction at the sub-sovereign level.

Mainstream assessments of Denmark's climate transition treat this heterogeneity as a distributional footnote. The Danish Climate Council's progress reports operate at national level; municipal finance analyses from VIVE focus on aggregate expenditure pressures. There is no systematic framework for tracing how transition shocks propagate through municipal sector accounts, accumulate as debt, and feed back to service delivery capacity.

### 1.2 Why Stock-Flow Consistency Matters

The core methodological argument of this thesis is that SFC modelling (Godley & Lavoie, 2007) provides the appropriate theoretical structure for this analysis — and that it has not been applied to subnational government heterogeneity in the context of climate transitions.

SFC models are built around the stock-flow consistency condition: every financial flow has a counterpart in another sector, and flows accumulate into stocks. For a municipal government sector, this produces the identity:

> **ΔL(t) = G(t) + I(t) − T(t)**

where ΔL is the change in long-term debt, G is current expenditure, I is capital investment, and T is total tax and grant revenue. A green transition shock that depresses T while raising G and I does not simply reduce the budget balance — it accumulates in the debt stock, reshaping the balance sheet and constraining future fiscal capacity in ways that conventional flow-based analysis misses.

This insight has been developed in closed-economy SFC models with ecological constraints (Dafermos, Nikolaidi & Galanis, 2017) and in national-level analyses of transition policy (Naqvi & Stockhammer, 2018). What is absent from this literature is any calibration to subnational heterogeneity — the systematic variation in transition exposure, fiscal starting conditions, and institutional capacity that determines whether the green transition is a manageable adjustment or a destabilising shock for specific localities.

### 1.3 The Danish Case as Ideal Research Setting

Denmark is the ideal laboratory for this analysis for four reasons:

1. **Data quality.** Statistics Denmark (DST) provides granular, time-consistent municipal finance, employment by NACE sector, demographic, and income data through open APIs, enabling calibration of SFC models at the municipal level.

2. **Transition ambition and timeline.** Denmark's 2030 target (70% emission reduction from 1990 levels) and the Heat Planning Act (2023) impose concrete, near-term transition requirements on municipalities, making the fiscal implications both measurable and policy-relevant.

3. **Institutional heterogeneity.** Denmark's 98 municipalities exhibit striking variation in fossil-sector employment share (from under 20% to over 45%), renewable energy intensity (from near-zero to 29 MW per 1,000 residents), and fiscal balance sheet health — the very heterogeneity the thesis seeks to explain.

4. **Policy relevance.** The Danish equalization system, transition grant mechanisms, and green investment co-financing schemes are all live policy levers. The thesis directly informs the design of these instruments.

---

## 2. Research Questions

1. **Heterogeneity:** How does climate exposure — combining physical risk and transition risk — interact with municipal fiscal starting conditions to produce differentiated vulnerability profiles across Danish municipalities, and what typology best captures this heterogeneity?

2. **SFC dynamics:** When calibrated to municipal-level sector accounts, what do SFC models reveal about the debt accumulation trajectories and fiscal resilience of high- versus low-exposure municipalities under alternative green transition pathways?

3. **Policy design:** Which combinations of green transition policy instruments — transition grants, green investment subsidies, tax-base stabilisation mechanisms — minimise fiscal stress in high-exposure municipalities while preserving macroeconomic coherence at the national level?

---

## 3. Proposed Methodology

The thesis follows a three-paper structure, progressing from empirical characterisation through theoretical modelling to policy analysis.

### Paper 1 — Climate-Fiscal Exposure Typology of Danish Municipalities

**Question:** What is the structure of climate-fiscal vulnerability heterogeneity across Danish municipalities?

**Data:** Statistics Denmark API (DST StatBank) — NACE employment by municipality (ERHV series), municipal financial accounts (REGNSKAB series), municipal income (INDKP series), demographic indicators. Energistyrelsen open data — renewable energy capacity by municipality. DMI climate observations — temperature trends, precipitation, extreme weather by municipality.

**Method:** I construct a **Transition Vulnerability Index (TVI)** combining:
- *Transition exposure:* fossil-linked NACE sector employment share (agriculture, conventional manufacturing, transport, fuel distribution)
- *Physical exposure:* climate baseline indicators (summer days, precipitation intensity, heating degree days)
- *Fiscal buffer:* long-term debt per capita, operating expenditure ratio, equalization grant dependency
- *Renewable readiness:* installed renewable capacity per 1,000 residents, green sector employment share

K-means clustering (k=4–6, selected by elbow and silhouette) identifies distinct municipality typologies: high-transition/high-physical, high-transition/low-fiscal-buffer, low-exposure/high-renewable, and mixed profiles. SHAP decomposition of the clustering model provides interpretable, indicator-level attribution for each typology.

Panel regressions (2013–2023) test whether TVI predicts fiscal balance deterioration, debt accumulation, and service expenditure pressure, controlling for population, income level, region fixed effects, and year fixed effects.

**Contribution:** First systematic empirical mapping of climate-fiscal exposure heterogeneity at Danish municipal level; the TVI provides a replicable diagnostic tool for green transition planning.

### Paper 2 — SFC Calibration and Fiscal Resilience under Transition Scenarios

**Question:** How do SFC dynamics differ between high- and low-exposure municipalities under alternative green transition pathways?

**Theoretical framework:** I develop a simplified two-sector SFC model for the municipal government sector, adapted from the government sector of Godley & Lavoie's (2007) canonical framework. The model tracks:

*Flows:* Tax revenue (T = τ · Y · e, where τ is the local tax rate, Y is average income, and e is the employment rate); operating expenditure (G); capital investment (I); central government transfers (T_g); net debt issuance (ΔL = G + I − T − T_g).

*Stocks:* Long-term debt (L); public capital stock (K_p); household financial wealth (W_h).

*Transition shock specification:* Green transition shocks are modelled as parametric perturbations to the tax base (through fossil-sector employment contraction) and to expenditure (through green infrastructure investment requirements), calibrated to observed NACE employment shares and municipality-level capital expenditure patterns.

I calibrate the model to two archetype municipalities drawn from Paper 1:
- **High exposure:** Municipality 0165 (Albertslund) — 42.7% fossil-linked employment, 34,159 DKK/capita debt, 0.2 MW/1,000 renewable intensity
- **Low exposure:** Municipality 0665 (Lemvig) — 31.2% fossil-linked employment, 15,043 DKK/capita debt, 28.9 MW/1,000 renewable intensity

Three transition scenarios are simulated over 2024–2034:
1. *Business-as-usual (BAU):* Current fiscal trajectory continues; small calibrated surplus assumption consistent with Danish local government balanced-budget requirement
2. *Accelerated transition:* Fossil employment contracts 25% over 2024–2026 (Phase 1 shock); green employment expands 2027–2030 (Phase 2); new steady state 2031–2034 (Phase 3)
3. *Policy-supported transition:* As scenario 2, but with transition grants (3,000 DKK/capita/year in Phase 1), green infrastructure co-financing, and tax-base stabilisation transfers

The model produces projected debt/capita and fiscal balance/capita trajectories under each scenario, comparing high- and low-exposure archetypes. Sensitivity analysis varies the fossil employment shock magnitude (15–35%), transition grant generosity, and the wage premium of green-sector employment.

**Contribution:** First calibration of a municipality-level SFC model to Danish data; demonstrates how stock-flow consistency reveals fiscal vulnerabilities that flow-based analysis conceals; provides a replicable simulation framework for transition policy assessment.

### Paper 3 — Policy Instrument Design for Fiscally Resilient Green Transition

**Question:** What policy instruments minimise fiscal stress in high-exposure municipalities while preserving national macroeconomic coherence?

**Framework:** Building on Paper 2's simulation infrastructure, this paper develops a multi-municipality SFC model that incorporates inter-governmental transfers explicitly. The model includes: the national government sector (setting transition grants, carbon revenue recycling, block grant formula); high-exposure municipalities (HEM); low-exposure municipalities (LEM); and a representative household sector.

I evaluate four families of instruments:

1. **Transition grants:** Direct per-capita transfers to high-exposure municipalities in Phase 1, calibrated to offset estimated tax-base contraction
2. **Green investment co-financing:** Central government matching of municipal green infrastructure capital expenditure, modelled as a reduction in ΔL for participating municipalities
3. **Tax-base stabilisation:** Graduated adjustments to the equalization formula that temporarily protect municipalities experiencing rapid fossil-sector employment decline
4. **Carbon revenue recycling:** Redistribution of carbon tax/ETS revenue to municipalities proportional to exposure, creating a green transition dividend for high-exposure areas

Evaluation criteria include: (a) fiscal balance trajectory for high-exposure municipalities; (b) debt stabilisation path; (c) aggregate national fiscal balance; (d) convergence of fiscal outcomes between high- and low-exposure municipalities over the simulation horizon.

The paper connects to the Post-Keynesian fiscal policy literature (Lavoie, 2014; Hein, 2014) on the design of functional finance in a heterogeneous institutional environment, and to the green transition fiscal policy literature (Pollin, 2015; Storm, 2017) on the macroeconomic conditions for a just transition.

**Contribution:** Develops an operational SFC-based policy evaluation framework for green transition fiscal instruments at the subnational level; directly relevant to Danish Ministry of Finance and Climate Council policy discussions.

---

## 4. Research Infrastructure: AreaStat DK

A functional research prototype has been developed to demonstrate the technical and empirical foundations of this thesis: **AreaStat DK** (https://rishikeshgovind.github.io/areastat-de/).

The platform implements:

| Component | Implementation |
|---|---|
| **DST data pipeline** | R scripts pulling 15+ DST StatBank series via open API; municipal-level annual panels |
| **Climate indicators** | Energistyrelsen renewable capacity; DMI temperature, precipitation, heating degree days |
| **Industry sector domains** | NACE employment shares by municipality (fossil vs green classification) |
| **SFCAccounts domain** | Derived per-capita government sector accounts (T, G, I, L, ΔL) for all 98 municipalities |
| **Transition Vulnerability Index** | Composite score: fossil share × relative debt burden, calibrated to Danish average |
| **Two-sector SFC scenario** | Prototype scenario simulation for Albertslund (high) vs Lemvig (low), 2024–2034 |
| **Transaction Flow Matrix** | Per-capita TFM and Balance Sheet Matrix for archetype municipalities |
| **Interactive visualisation** | Chart.js scenario projection charts with phase annotations; ML export for cluster analysis |

This infrastructure directly underpins the empirical work in Papers 1 and 2, and provides a stakeholder engagement tool for Paper 3's policy analysis.

---

## 5. Data Sources

| Data | Source | Coverage |
|---|---|---|
| Municipal fiscal accounts | Statistics Denmark StatBank (REGNSKAB series) | 98 municipalities, 2013–2023 |
| Municipal income and employment | DST StatBank (INDKP, ERHV series) | 98 municipalities, annual |
| NACE sector employment by municipality | DST StatBank (RAS series) | 98 municipalities, 2013–2022 |
| Renewable energy capacity | Energistyrelsen (Stamdataregisteret) | Municipality-level, annual |
| Climate observations | DMI open data (temperature, precipitation, extreme weather) | Station-level, aggregated to municipality |
| Green transition plans | Municipal climate action plans (Klimapartnerskaber) | Where available |
| Equalization and block grants | DST StatBank (KOMMUNALUDLIGN) | 98 municipalities, annual |
| National accounts sectoral data | Statistics Denmark (ADAM model data) | National, for SFC calibration |

---

## 6. Theoretical Positioning and Literature Engagement

This thesis is explicitly situated within the Post-Keynesian and ecological macroeconomics tradition, and engages with the following strands of literature:

**Stock-Flow Consistent Macroeconomics.** Godley & Lavoie (2007) establish the canonical SFC framework. Dos Santos & Zezza (2008) and Caverzasi & Godin (2015) provide methodological extensions. Dafermos et al. (2017, 2019) develop SFC models with ecological constraints, closest to the framework proposed here. This thesis extends this literature to the subnational government sector and to empirical calibration at the municipal level — a methodological gap the existing literature has not addressed.

**Minsky and Financial Fragility.** Minsky's (1986) financial instability hypothesis provides the conceptual anchor for understanding how fiscal flows deteriorate into balance-sheet fragility. Vercelli (2009) and Palley (2010) develop the Minskyan analysis of non-financial sectors. I apply the Ponzi/speculative/hedge taxonomy to municipal fiscal positions, arguing that high-exposure municipalities face a risk of transition-induced deterioration from hedge to speculative fiscal posture.

**Green Transition and Post-Keynesian Macroeconomics.** Storm (2017, 2020), Pettifor (2019), and Nersisyan & Wray (2019) develop Post-Keynesian perspectives on the green transition and public finance. The distributional and spatial dimensions of the transition are emphasised in Gough (2017) and Räthzel & Uzzell (2011). This thesis contributes a rigorous subnational SFC empirical framework to this debate.

**Ecological SFC Models.** Dafermos, Nikolaidi & Galanis (2017) is the foundational reference; Caiani et al. (2016) and Montes-Rojas (2020) provide additional methodological resources. The present thesis adapts these frameworks to government sector dynamics in a small open economy.

**Danish Municipal Finance.** VIVE reports on kommunal økonomi, KL (Local Government Denmark) publications on climate finance, and the Danish Ministry of Finance's municipal finance frameworks provide the institutional grounding.

---

## 7. Expected Contributions

**Theoretical:** First application of calibrated SFC modelling to subnational government heterogeneity in the context of a green energy transition. Extends the ecological SFC literature (Dafermos et al., 2017) from closed-economy representative agents to an explicitly heterogeneous, data-calibrated multi-municipality framework.

**Empirical:** First systematic Transition Vulnerability Index for all 98 Danish municipalities, combining fiscal, energy, and climate indicators. The resulting panel dataset will be made publicly available via AreaStat DK.

**Policy:** Operational SFC-based evaluation framework for green transition fiscal instruments. Directly applicable to the design of Danish transition grants, climate equalization adjustments, and green infrastructure co-financing under the Heat Planning Act.

**Methodological:** Demonstrates a replicable pipeline — from open government data APIs to SFC-calibrated sector accounts — applicable to other small open economies undertaking green transitions (Sweden, Netherlands, Finland).

---

## 8. Candidate Background

I hold an MSc in Risk and Investment Management, providing a foundation in quantitative finance, credit risk modelling, and portfolio theory. Prior research experience includes work with official administrative microdata at the Northern Ireland Statistics and Research Agency (NISRA).

For this proposal, I have already developed a complete empirical research infrastructure. The AreaStat DK platform implements all four phases of the research agenda:

- **Phase 1 (Data):** Full DST API pipeline; GreenEnergy, ClimateBaseline, GreenTransition, and IndustrySectors domains constructed from Energistyrelsen and DST sources for all 98 municipalities
- **Phase 2 (Analytics):** K-means clustering with climate variables; Transition Vulnerability Index computation; sector-composition-aware unemployment model reframing
- **Phase 3 (SFC framing):** SFCAccounts domain (per-capita T, G, I, L, ΔL, capital stock, net financial worth) for all 98 municipalities; Transaction Flow Matrix and Balance Sheet Matrix for archetype municipalities; two-sector SFC prototype scenario for Albertslund (high exposure) vs Lemvig (low exposure), 2024–2034
- **Phase 4 (This proposal):** Theoretical framing within Post-Keynesian SFC literature; connection to MaMTEP's research agenda

This infrastructure demonstrates both technical feasibility and conceptual alignment with the proposed PhD research. The platform is live and publicly accessible.

---

## 9. Fit with Aalborg MaMTEP

The MaMTEP programme's distinctive contribution to economic thought — rigorous engagement with heterodox macroeconomics, institutional economics, and the critique of mainstream orthodoxy — aligns directly with this thesis's theoretical foundations. Specifically:

- The SFC framework is a central methodological tool in Post-Keynesian macroeconomics and is actively researched and taught at Aalborg
- The focus on green transition policy design connects to MaMTEP's engagement with industrial and ecological policy
- The emphasis on heterogeneity, institutions, and distributional dynamics is a defining feature of both the programme and this thesis
- The Danish empirical setting allows direct engagement with ongoing policy debates in which Aalborg researchers are active participants

I am particularly interested in working with faculty whose research addresses Post-Keynesian macroeconomics, ecological economics, and/or climate transition policy within a heterodox framework.

---

## 10. Indicative Timeline

| Period | Milestones |
|---|---|
| Year 1, Q1–Q2 | Literature review; extend AreaStat DK data pipeline; finalise TVI methodology |
| Year 1, Q3–Q4 | Paper 1 empirical analysis (clustering, TVI panel regressions); draft Paper 1 |
| Year 2, Q1–Q2 | Paper 1 submission; SFC model development and calibration; Paper 2 draft |
| Year 2, Q3–Q4 | Paper 2 submission; multi-municipality SFC extension; policy instrument analysis |
| Year 3, Q1–Q2 | Paper 3 (policy design) analysis and draft; policy stakeholder engagement |
| Year 3, Q3–Q4 | Paper 3 submission; thesis compilation; defence preparation |

---

## 11. References

- Caiani, A., Godin, A., Caverzasi, E., Gallegati, M., Kinsella, S., & Stiglitz, J. E. (2016). Agent based-stock flow consistent macroeconomics: Towards a benchmark model. *Journal of Economic Dynamics and Control*, 69, 375–408.
- Caverzasi, E., & Godin, A. (2015). Post-Keynesian stock-flow-consistent modelling: A survey. *Cambridge Journal of Economics*, 39(1), 157–187.
- Dafermos, Y., Nikolaidi, M., & Galanis, G. (2017). A stock-flow-fund ecological macroeconomic model. *Ecological Economics*, 131, 191–207.
- Dafermos, Y., Nikolaidi, M., & Galanis, G. (2019). Climate change, financial stability and monetary policy. *Ecological Economics*, 152, 219–234.
- Danish Climate Council (2023). *Status on Denmark's Climate Targets and Green Transition.* Copenhagen.
- Dos Santos, C. H., & Zezza, G. (2008). A simplified, 'benchmark', stock-flow consistent Post-Keynesian growth model. *Metroeconomica*, 59(3), 441–478.
- Godley, W., & Lavoie, M. (2007). *Monetary Economics: An Integrated Approach to Credit, Money, Income, Production and Wealth.* Palgrave Macmillan.
- Gough, I. (2017). *Heat, Greed and Human Need: Climate Change, Capitalism and Sustainable Wellbeing.* Edward Elgar.
- Hein, E. (2014). *Distribution and Growth After Keynes: A Post-Keynesian Guide.* Edward Elgar.
- KL — Local Government Denmark (2023). *Kommunernes Klimahandlingsplaner: Status og perspektiver.*
- Lavoie, M. (2014). *Post-Keynesian Economics: New Foundations.* Edward Elgar.
- Minsky, H. P. (1986). *Stabilizing an Unstable Economy.* Yale University Press.
- Naqvi, A., & Stockhammer, E. (2018). Directed technical change in a post-Keynesian ecological macromodel. *Ecological Economics*, 154, 168–188.
- Nersisyan, Y., & Wray, L. R. (2019). How to pay for the Green New Deal. *Levy Economics Institute Working Paper*, No. 931.
- Palley, T. I. (2010). The limits of Minsky's financial instability hypothesis as an explanation of the crisis. *Monthly Review*, 61(11).
- Pettifor, A. (2019). *The Case for the Green New Deal.* Verso.
- Pollin, R. (2015). *Greening the Global Economy.* MIT Press.
- Storm, S. (2017). The new normal: Demand, secular stagnation, and the vanishing middle class. *International Journal of Political Economy*, 46(4), 169–210.
- Storm, S. (2020). Cordon of conformity: Why IPCC reports underestimate the risks of climate change. *Social Europe.* Working paper.
- Vercelli, A. (2009). A perspective on Minsky moments: The core of the financial instability hypothesis in light of the subprime crisis. *Levy Economics Institute Working Paper*, No. 579.
- VIVE — The Danish Centre for Social Science Research (2022). *Kommunernes økonomi: Strukturelle udfordringer og grøn omstilling.*
