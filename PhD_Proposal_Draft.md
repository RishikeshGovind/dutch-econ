# PhD Research Proposal

**Title:** Decision-Focused Learning in Modern Operations: Integrating Predictive Models with Optimization Across Energy, Healthcare, and Logistics

**Position:** PhD in Econometrics, Operations Research and Social Choice — Project 1 (Data-driven decision making in modern operations)

**Department of Quantitative Economics, School of Business and Economics, Maastricht University**

---

## Abstract

Most organisations that use machine learning to make operational decisions face the same hidden problem. The forecast model is trained to be accurate, but the thing that actually matters is whether accurate forecasts lead to better decisions. These two objectives are not the same. In battery energy storage, a forecast error that does not change the charge or discharge decision is harmless. The same error at a different hour can cost hundreds of euros. In hospital staffing, being short by one nurse is far more expensive than having one nurse too many, but standard training treats both errors identically.

This research develops and evaluates decision-focused learning methods — specifically Smart Predict-Then-Optimize, SPO+ (Elmachtoub & Grigas, 2022) — that train predictive models with the downstream optimization problem explicitly in the loss function. The central research question is not whether SPO+ works, but *when* it works, *by how much*, and across *which types of optimization problems*. A working prototype covering three of the PhD call's named industry partners demonstrates both the problem and the open questions.

---

## 1. The Research Problem

### 1.1 Predict-then-optimize and its flaw

The standard pipeline for data-driven operations runs in two separate stages. First, a machine learning model produces a forecast. Second, a planning tool uses that forecast to make a decision. The model is trained by minimising a loss on its predictions, typically mean squared error. The planning tool optimises separately. The two stages never communicate during training.

This works when every prediction error is equally costly. In practice, errors are almost never equally costly. Elmachtoub & Grigas (2022) formalise this observation: the right training objective is not "how close was the prediction to the truth" but "how much did the prediction cost in terms of the downstream decision quality." They call the gap between the decision made under a forecast and the decision that would have been made with perfect information the *decision regret*, and propose SPO+, a method that replaces the MSE gradient with a decision-regret gradient during training.

The key insight is that SPO+ only adjusts the model at the hours or data points where a forecast error actually changed the decision. Hours where both the standard model and the oracle would have made the same decision get zero gradient signal. This concentrates the model's learning capacity on the errors that matter operationally.

### 1.2 What is still unknown

The SPO+ paper (Elmachtoub & Grigas, 2022) demonstrates the method on stylised problems. The 2024 JAIR survey by Mandi et al. identifies three open problems that this PhD addresses directly:

1. **Conditions for SPO+ to win.** SPO+ outperforms standard training when decision-sensitive hours have learnable structure — a recurring pattern the model can exploit. When every hour is equally sensitive (uniform sensitivity), SPO+ and standard training converge. The Oct-Nov 2024 ENTSO-E test set in Case 1 of this demo illustrates this: 92.7% of hours flip the battery decision under a 10 EUR/MWh perturbation. With near-uniform sensitivity, SPO+ earns similar revenue to standard XGBoost. Measuring where and when the conditions for SPO+ gains are met — across market regimes, seasonal patterns, and problem types — is the primary contribution of this thesis.

2. **Time-coupled constraints.** The original SPO+ formulation treats each prediction independently. Battery dispatch is a sequential problem: the state of charge at hour *t* constrains what is possible at *t+1*. Hospital shift handovers create similar cross-period dependencies. Extending SPO+ to handle these time-coupled structures is a theoretical contribution not yet in the literature.

3. **Non-differentiable optimizers.** SPO+ works cleanly when the optimizer is a linear program, because the LP dual provides the decision gradient. Vehicle routing at realistic scale requires heuristics (nearest-neighbour, 2-opt), which have no clean gradient. Developing surrogate gradient methods that extend SPO+ to heuristic solvers is the most novel and technically challenging part of this research.

---

## 2. Research Questions

**RQ1 — Conditions:** Under what market conditions, data structures, and problem types does decision-focused training (SPO+) produce meaningful gains over standard predict-then-optimize? What is the relationship between the distribution of decision sensitivity across time and the realized gain from decision-focused training?

**RQ2 — Time coupling:** How can the SPO+ gradient be extended to operational problems with sequential state constraints (battery state of charge, shift continuity, vehicle capacity carry-over)?

**RQ3 — Heuristic optimizers:** What surrogate gradient methods enable decision-focused training when the downstream optimizer is a heuristic that cannot be differentiated directly?

**RQ4 — Explainability:** Can decision-level attribution — identifying which input features caused which operational decisions to flip — be developed as a practical transparency tool for managers?

---

## 3. Methodology

### 3.1 Common pipeline across all three cases

All three case studies use the same five-stage architecture:

1. **Data collection and feature engineering.** Real or calibrated operational data from Dutch sources (ENTSO-E, LCPS, RIVM, NZa, CBS, OpenStreetMap).
2. **Forecast model training.** XGBoost trained first with MSE loss (baseline) and then with the SPO+ decision-regret loss (intervention).
3. **Optimizer.** Linear program (Cases 1 and 2) or routing heuristic (Case 3). The structure of this stage is what differentiates the research problems.
4. **Decision.** Charge/discharge schedule, nurse staffing level, or delivery routes — evaluated at realised costs, not at prediction error.
5. **Regret measurement.** Revenue gap vs oracle (Case 1), staffing cost overage (Case 2), extra kilometres vs best-known route (Case 3).

### 3.2 Case 1 — Battery dispatch (LP, differentiable)

A 1 MW / 2 MWh battery arbitrages the Dutch day-ahead electricity market. XGBoost trained on 34,320 hourly observations from the ENTSO-E Transparency Platform (January 2021 to November 2024) produces the price forecast. The LP dispatch is formulated with hourly charge and discharge decisions subject to state-of-charge dynamics and power limits.

The prototype implements three training variants alongside the MSE baseline:
- **Regret-weighted XGBoost:** sample weights proportional to daily dispatch regret under the current model
- **SPO+ gradient correction:** iterative correction using the LP dual — the decision gradient at hour *t* is the price error multiplied by the change in the net dispatch decision (discharge minus charge) between the oracle and naive LP

The 60-day test period (October to November 2024) shows that all three variants earn similar revenue (SPO+ 19.8% of oracle, standard XGBoost 21.0%, regret-weighted 22.6%). Decision sensitivity analysis reveals that 92.7% of test hours would flip the battery decision under a ±10 EUR/MWh perturbation — near-uniform sensitivity across hours. This explains the similar performance: there is no specific cluster of hours for SPO+ to target. The research question becomes: under what market conditions does structured sensitivity emerge, and how much does SPO+ gain when it does?

**Uncertainty quantification.** The prototype adds 80% conformal prediction intervals using Split Conformal Quantile Regression (Romano, Sesia & Candès, 2019), achieving 85.5% empirical coverage on the test set (above the 80% guarantee, as expected). A robust dispatch strategy using lower-bound prices as LP inputs earns €13,164 vs €13,440 for the standard strategy — a small revenue cost in exchange for fewer positions taken on uncertain forecasts.

### 3.3 Case 2 — Hospital staffing (LP with asymmetric penalty)

A teaching hospital calibrated on Maastricht UMC+ data forecasts next-day ICU admissions and solves a staffing LP where being one nurse short costs approximately 4× more than having one nurse idle. The asymmetric penalty structure creates a directional bias: SPO+ should learn to over-forecast admissions rather than to be accurate in expectation.

This case tests the RQ2 extension: shift continuity (handover constraints between morning and evening shifts) creates cross-period dependencies similar to SOC dynamics in the battery case.

Data sources: LCPS national ICU bed registry, RIVM admission rates, NZa production volumes, CBS demographic statistics.

### 3.4 Case 3 — Logistics routing (heuristic optimizer, non-differentiable)

A Dutch parcel carrier forecasts daily demand by postcode zone and plans routes using a Capacitated VRP heuristic. At 12 zones, the routing problem is solved with nearest-neighbour and 2-opt improvement rather than exact methods.

This case addresses RQ3 directly: the routing heuristic has no analytic gradient, so the SPO+ training signal cannot be computed directly. The research will develop and evaluate two families of surrogate gradient methods:
- **Perturbation-based:** evaluate the heuristic at perturbed cost vectors and estimate the gradient numerically
- **Smoothed LP relaxation:** relax the integer routing constraints into a continuous LP, compute the SPO+ gradient there, and use it as a proxy

Data sources: CBS Kerncijfers wijken en buurten (postcode-level demographics), OpenStreetMap Netherlands road network, RDW fleet data.

---

## 4. Key Prototype Results

| | Case 1 (Energy) | Case 2 (Hospital) | Case 3 (Logistics) |
|---|---|---|---|
| **Optimizer** | LP (linear) | LP (asymmetric penalty) | VRP heuristic |
| **SPO+ status** | Implemented | Implemented | Prototype |
| **Revenue / cost gap** | Oracle €12,567, naive €4,057 (68% gap) | Demonstrated | 39% route distance gap (NN vs benchmark) |
| **Key finding** | Uniform sensitivity limits SPO+ gain in autumn 2024 market | Asymmetric penalty changes the direction of optimal errors | Heuristic non-differentiability is the core open problem |
| **Open research** | When does structured sensitivity emerge? | Time-coupled LP extension | Surrogate gradient methods |

---

## 5. Literature

**Decision-focused learning (core)**
- Elmachtoub & Grigas (2022). Smart Predict-Then-Optimize. *Management Science* 68(1). — The foundational SPO+ paper; the prototype implements this directly.
- Mandi, Kotary, Berden et al. (2024). Decision-Focused Learning: Foundations, State of the Art, Benchmark and Future Opportunities. *JAIR* 80. — Definitive 2024 survey; identifies the three open problems this PhD addresses.
- Sadana, Mathieu, Jackobson & Bengio (2024). A Survey of Predict-Then-Optimize Methods. *ACM Computing Surveys*. — Broader survey for literature review framing.
- Wilder, Dilkina & Tambe (2019). Melding the Data-Decisions Pipeline: Decision-Focused Learning for Combinatorial Optimization. *AAAI*. — Extends SPO+ to combinatorial (integer) problems, directly relevant to Case 3.

**Uncertainty quantification**
- Romano, Sesia & Candès (2019). Conformal Quantile Regression. *NeurIPS*. — The CQR method used in Case 1 for prediction intervals with guaranteed coverage.
- Dumas, Wehenkel, Lanaspeze et al. (2022). A deep learning-based approach for quantile regression in energy systems. *Energy*. — Probabilistic forecasting for battery dispatch, extends the deterministic XGBoost baseline.

**Energy storage and electricity markets**
- Macdonald, Clack, McDonald et al. (2023). Learning to optimize under uncertainty: Energy storage dispatch. *IEEE Transactions on Power Systems*. — Near-identical problem setup; useful for benchmarking.

**Explainability in operations**
- Lundberg & Lee (2017). A unified approach to interpreting model predictions (SHAP). *NeurIPS*. — The prototype computes SHAP values; the research extends attribution to decision space rather than prediction space.

---

## 6. Fit with Maastricht SBE

The Department of Quantitative Economics brings together econometrics, operations research, machine learning, and game theory in one department — the exact combination this research requires. The three industry partners named in the PhD call (university hospital, last-mile logistics providers, energy companies) are all covered in this prototype.

The research contributes to each methodological strand of the department:
- **Operations research:** new LP-compatible and heuristic-compatible training algorithms
- **Econometrics / machine learning:** decision-focused learning, conformal prediction, interpretable models
- **Applied work:** real Dutch data from ENTSO-E, LCPS, RIVM, CBS; real-world partners for empirical validation

The research is positioned within Project 1 of the current PhD call. The prototype demonstrates technical feasibility and a concrete understanding of where the open research problems lie.

---

## 7. Candidate Background

MSc in Risk and Investment Management, with foundations in quantitative finance, credit risk, and portfolio optimisation. Prior research experience includes work with administrative microdata at NISRA (Northern Ireland Statistics and Research Agency).

For this application I have built a complete working prototype covering all three named partner domains. The prototype includes:
- A live ENTSO-E data pipeline (34,320 hourly observations, Jan 2021 – Nov 2024)
- A functioning SPO+ gradient implementation and comparison against MSE and regret-weighted baselines
- Conformal quantile regression with verified 85.5% empirical coverage
- Decision sensitivity analysis (per-hour flip rates and revenue impact)
- SHAP feature attribution
- Hospital and logistics case studies with calibrated data

The prototype is deployed at [github.io link] and the full source is available in this repository.

---

## 8. Timeline

| Period | Milestones |
|---|---|
| Year 1, Q1-Q2 | Literature review; formalise SPO+ extension to time-coupled LPs; refine Case 1 theory |
| Year 1, Q3-Q4 | Empirical study of when SPO+ wins (conditions on sensitivity distribution); Paper 1 draft |
| Year 2, Q1-Q2 | Paper 1 submission; hospital Case 2 full empirical study with Maastricht UMC+ data |
| Year 2, Q3-Q4 | Paper 2 draft and submission; begin Case 3 surrogate gradient development |
| Year 3, Q1-Q2 | Case 3 experiments (perturbation-based and relaxation-based gradients); Paper 3 draft |
| Year 3, Q3-Q4 | Paper 3 submission; thesis compilation; defence preparation |

---

## 9. References

- Dumas, J., Wehenkel, A., Lanaspeze, D., Cornélusse, B., & Sutera, A. (2022). A deep learning-based approach for quantile regression in energy systems: Application to short-term load forecasting. *Energy*, 238, 121929.
- Elmachtoub, A. N., & Grigas, P. (2022). Smart predict-then-optimize. *Management Science*, 68(1), 9–26.
- Lundberg, S. M., & Lee, S. I. (2017). A unified approach to interpreting model predictions. *Advances in Neural Information Processing Systems*, 30.
- Mandi, J., Kotary, J., Berden, S., Mulamba, M., Bucarey, V., Guns, T., & Passerini, A. (2024). Decision-focused learning: Foundations, state of the art, benchmark and future opportunities. *Journal of Artificial Intelligence Research*, 80, 1065–1148.
- Romano, Y., Sesia, M., & Candès, E. (2019). Conformalized quantile regression. *Advances in Neural Information Processing Systems*, 32.
- Sadana, U., Mathieu, A., Jackobson, E., & Bengio, Y. (2024). A survey of predict-then-optimize methods for stochastic combinatorial optimization. *ACM Computing Surveys*, 57(1).
- Wilder, B., Dilkina, B., & Tambe, M. (2019). Melding the data-decisions pipeline: Decision-focused learning for combinatorial optimization. *Proceedings of the AAAI Conference on Artificial Intelligence*, 33(1), 1658–1665.
