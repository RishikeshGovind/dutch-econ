"""
Phase 3 — SFC Framing
Adds SFCAccounts domain to every municipality and a top-level sfc_scenario
block with prototype two-sector SFC simulations (high vs low climate exposure).

Key methodological choice:
  Municipalities run approximately balanced budgets by law (Danish LBK § 46).
  We therefore calibrate to a small BAU surplus (0.5 % of total spending) and
  model the DEVIATION from that baseline caused by the green transition.

SFC identity:  ΔL(t) = G(t) + I(t) - T(t)   [deficit → debt accumulation]
"""

import json

INPUT  = 'data.json'
OUTPUT = 'data.json'

with open(INPUT, encoding='utf-8') as f:
    data = json.load(f)

kommuner = data['Kommune']


def sc(v):
    if isinstance(v, (int, float)): return v
    if isinstance(v, list) and v:   return v[0]
    return None


dk_fin      = data['Denmark Total'].get('Financial', {})
avg_debt_dk = sc(dk_fin.get('Long-term debt/capita (DKK)')) or 12397


# ──────────────────────────────────────────────────────────────────────────────
# 1.  SFCAccounts domain — all municipalities
# ──────────────────────────────────────────────────────────────────────────────

for kid, kd in kommuner.items():
    fin = kd.get('Financial', {})
    fp  = kd.get('FiscalPolicy', {})
    eco = kd.get('Economy', {})
    lm  = kd.get('LabourMarket', {})
    gt  = kd.get('GreenTransition', {})
    cb  = kd.get('ClimateBaseline', {})

    debt_cap   = sc(fin.get('Long-term debt/capita (DKK)'))
    ops_cap    = sc(fin.get('Operating expenses/capita (DKK)'))
    capex_cap  = sc(fin.get('Capital expenditures/capita (DKK)'))
    grants_cap = sc(fin.get('Equalization grants/capita (DKK)'))
    tax_rate   = sc(fp.get('Municipal income tax rate (%)'))
    avg_inc    = sc(eco.get('Avg income (DKK)'))
    emp_rate   = sc(lm.get('Employment rate (%)'))
    fossil_pct = sc(gt.get('Fossil-linked sector share (%)'))
    renew_int  = sc(gt.get('Renewable intensity (MW/1,000)'))
    summer_d   = sc(cb.get('Summer days per year (>25°C)'))

    # Estimated municipal income-tax revenue (per employed resident × tax rate)
    t_tax_cap = None
    if tax_rate is not None and avg_inc is not None and emp_rate is not None:
        t_tax_cap = round((tax_rate / 100) * avg_inc * (emp_rate / 100), 0)

    # Estimated total expenditure (spending side is observable)
    total_exp_cap = None
    if ops_cap is not None:
        total_exp_cap = round((ops_cap or 0) + (capex_cap or 0), 0)

    # Calibrated revenue: assume approximate budget balance (legal requirement).
    # The gap between income-tax + equalization and total spending is covered by
    # state block grants and local fees, which we do not observe separately.
    # We record only the SFC-compatible components we CAN estimate.
    t_tax_note = 'estimated from tax rate × avg income × employment rate'

    # ΔL ≈ -(T−G−I) — we compute this from the identifiable components only.
    # A positive ΔL means net debt issuance (deficit financing).
    delta_L_cap = None
    if t_tax_cap is not None and grants_cap is not None and total_exp_cap is not None:
        partial_rev = t_tax_cap + grants_cap          # income-tax + equalisation
        partial_bal = partial_rev - total_exp_cap     # negative → deficit w.r.t. these flows
        delta_L_cap = round(-partial_bal, 0)          # sign convention: positive = new debt

    # Balance-sheet stocks
    capital_stock_cap = round((debt_cap or 0) + 8 * (capex_cap or 0), 0)
    net_financial_cap = round(-(debt_cap or 0), 0)

    # Climate risk indices
    phys_score  = round((summer_d or 0) / 20 * 100, 1)
    if fossil_pct is not None and renew_int is not None:
        trans_score = round(fossil_pct + max(0, 10 - renew_int) * 2, 1)
    elif fossil_pct is not None:
        trans_score = round(fossil_pct, 1)
    else:
        trans_score = None

    trans_vuln = None
    if fossil_pct is not None and debt_cap is not None:
        trans_vuln = round((fossil_pct / 100) * (debt_cap / avg_debt_dk), 3)

    kd['SFCAccounts'] = {
        # Government sector — flows (per capita, DKK)
        'T_tax_per_capita (DKK)':             t_tax_cap,
        'T_grants_equalization_per_capita (DKK)': grants_cap,
        'G_ops_per_capita (DKK)':             ops_cap,
        'I_capital_per_capita (DKK)':         capex_cap,
        'Total_expenditure_per_capita (DKK)': total_exp_cap,
        'Delta_L_partial_per_capita (DKK)':   delta_L_cap,
        # Balance-sheet stocks (per capita, DKK)
        'L_debt_per_capita (DKK)':            debt_cap,
        'Capital_stock_per_capita (DKK)':     capital_stock_cap,
        'Net_financial_worth_per_capita (DKK)': net_financial_cap,
        # Climate composite indices
        'Climate_physical_score':             phys_score,
        'Climate_transition_score':           trans_score,
        'Transition_vulnerability_index':     trans_vuln,
        'Note': t_tax_note,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 2.  Prototype two-sector SFC scenario
# ──────────────────────────────────────────────────────────────────────────────

ARCHETYPES = {
    'high_exposure': {'id': '0165', 'name': 'Albertslund'},
    'low_exposure':  {'id': '0665', 'name': 'Lemvig'},
}

YEARS = list(range(2024, 2035))   # 11 projection years


def run_scenario(kid):
    """
    Calibrated SFC scenario simulation.

    BAU calibration
    ---------------
    Danish municipalities are legally required to maintain balanced budgets
    (LBK no. 318 § 46).  We therefore calibrate a small BAU surplus equal to
    0.5 % of total spending per year.  This surplus grows at (revenue_growth −
    spending_growth) = 0.5 % pa as wages outpace spending over time.

    Green Transition deviation
    --------------------------
    We model the INCREMENT to fiscal balance relative to BAU caused by:
      Phase 1 (years 0-2): fossil-sector employment shock
        • Income-tax revenue contracts: emp_rate × fossil_share × 25 % × income × tax_rate
        • Extra capex for green infrastructure: +15 % of baseline
        • Central-gov transition grant: +3,000 DKK/cap pa
      Phase 2 (years 3-6): gradual recovery
        • Tax-base loss tapers as green employment grows
        • Transition grants phase out
      Phase 3 (years 7-10): new steady state
        • Small permanent fossil-employment loss (~10 % of Phase 1 magnitude)
        • Green-economy income premium: +5 % income premium for fossil_share of workers
    """
    kd = kommuner[kid]
    fin = kd.get('Financial', {})
    fp  = kd.get('FiscalPolicy', {})
    eco = kd.get('Economy', {})
    lm  = kd.get('LabourMarket', {})
    gt  = kd.get('GreenTransition', {})

    debt0      = sc(fin.get('Long-term debt/capita (DKK)'))       or 15000
    ops0       = sc(fin.get('Operating expenses/capita (DKK)'))   or 80000
    capex0     = sc(fin.get('Capital expenditures/capita (DKK)')) or 3000
    tax_rate   = sc(fp.get('Municipal income tax rate (%)'))      or 25.0
    avg_inc0   = sc(eco.get('Avg income (DKK)'))                  or 250000
    emp_rate0  = sc(lm.get('Employment rate (%)'))                or 75.0
    fossil_pct = sc(gt.get('Fossil-linked sector share (%)'))     or 30.0

    fossil_share = fossil_pct / 100.0
    total_spend0 = ops0 + capex0

    # BAU calibration: small surplus, improving over time
    bau_surplus0 = total_spend0 * 0.005     # ~0.5 % of spending
    surplus_growth = 0.005                  # revenue grows 0.5 pp faster than spending

    # Tax-base contraction per year if fossil sector contracts 25 % in Phase 1
    # = (employed pop / cap) × fossil_share × 25 % × avg_income × tax_rate
    tax_loss_p1 = (emp_rate0 / 100) * fossil_share * 0.25 * avg_inc0 * (tax_rate / 100)

    # ── BAU ──────────────────────────────────────────────────────────────────
    bau = {'debt': [], 'fiscal_balance': [], 'avg_income': [], 'employment_rate': []}
    debt = debt0
    for i in range(len(YEARS)):
        surplus = bau_surplus0 * ((1 + surplus_growth) ** i)
        debt   -= surplus
        bau['debt'].append(round(debt))
        bau['fiscal_balance'].append(round(surplus))
        bau['avg_income'].append(round(avg_inc0 * (1.02 ** i)))
        bau['employment_rate'].append(round(emp_rate0, 1))

    # ── Green Transition ─────────────────────────────────────────────────────
    gt_scen = {'debt': [], 'fiscal_balance': [], 'avg_income': [], 'employment_rate': []}
    debt = debt0
    for i in range(len(YEARS)):
        bau_surplus_i = bau_surplus0 * ((1 + surplus_growth) ** i)

        if i < 3:
            # Phase 1: shock
            tax_loss     = tax_loss_p1
            extra_capex  = capex0 * 0.15
            trans_grant  = 3000.0
            emp_adj_rate = emp_rate0 * (1 - fossil_share * 0.25)
            inc_factor   = 0.98
        elif i < 7:
            # Phase 2: recovery — tax loss and extra capex taper linearly
            frac_recovered = (i - 3) / 4.0          # 0 → 1 over 4 years
            tax_loss       = tax_loss_p1 * (1 - frac_recovered)
            extra_capex    = capex0 * 0.08 * (1 - frac_recovered)
            trans_grant    = max(0.0, 3000 - (i - 3) * 750)
            emp_adj_rate   = emp_rate0 * (1 - fossil_share * 0.15 * (1 - frac_recovered))
            inc_factor     = 1.0 + (i - 3) * 0.005
        else:
            # Phase 3: new steady state
            # Permanent loss: 10 % of Phase 1 magnitude; green premium offsets
            perm_tax_loss  = tax_loss_p1 * 0.10
            green_premium  = avg_inc0 * (1.02 ** i) * (emp_rate0 / 100) * fossil_share * 0.05 * (tax_rate / 100)
            tax_loss       = perm_tax_loss - green_premium  # may be negative (net gain)
            extra_capex    = 0.0
            trans_grant    = 0.0
            emp_adj_rate   = emp_rate0 * (1 - fossil_share * 0.10)
            inc_factor     = 1.02

        # Deviation from BAU: worse if net_delta negative
        net_delta = -tax_loss - extra_capex + trans_grant
        surplus   = bau_surplus_i + net_delta
        debt     -= surplus

        gt_scen['debt'].append(round(debt))
        gt_scen['fiscal_balance'].append(round(surplus))
        gt_scen['avg_income'].append(round(avg_inc0 * (1.02 ** i) * inc_factor))
        gt_scen['employment_rate'].append(round(emp_adj_rate, 1))

    return {'bau': bau, 'green_transition': gt_scen}


def build_tfm(kid):
    """Transaction Flow Matrix — government sector (per capita, DKK)."""
    kd  = kommuner[kid]
    sfc = kd.get('SFCAccounts', {})
    eco = kd.get('Economy', {})

    t_tax   = sfc.get('T_tax_per_capita (DKK)')
    grants  = sfc.get('T_grants_equalization_per_capita (DKK)')
    g_ops   = sfc.get('G_ops_per_capita (DKK)')
    i_cap   = sfc.get('I_capital_per_capita (DKK)')
    debt    = sfc.get('L_debt_per_capita (DKK)')
    avg_inc = sc(eco.get('Avg income (DKK)'))

    return {
        'rows': [
            {'label': 'Municipal income tax (T_tax)',
             'gov': t_tax, 'hh': None if t_tax is None else -t_tax},
            {'label': 'State equalisation transfers (T_grants)',
             'gov': grants, 'hh': None},
            {'label': 'State block grants (T_block)',
             'gov': 'n/a — calibrated residual', 'hh': None},
            {'label': 'Government consumption (G)',
             'gov': None if g_ops is None else -g_ops, 'hh': g_ops},
            {'label': 'Capital investment (I)',
             'gov': None if i_cap is None else -i_cap, 'hh': None},
            {'label': 'Net debt issuance (ΔL)',
             'gov': '≈ 0 (balanced budget)', 'hh': None},
        ],
        'debt_stock': debt,
        'avg_income': avg_inc,
        'note': 'Block grants are not individually observable; T_tax and equalisation shown.',
    }


def build_bsm(kid):
    """Balance Sheet Matrix (per capita, DKK)."""
    kd  = kommuner[kid]
    sfc = kd.get('SFCAccounts', {})
    eco = kd.get('Economy', {})
    avg_inc = sc(eco.get('Avg income (DKK)'))
    debt    = sfc.get('L_debt_per_capita (DKK)')
    cap_stk = sfc.get('Capital_stock_per_capita (DKK)')

    hh_wealth = round(avg_inc * 2.5) if avg_inc else None    # proxy: 2.5× income

    return {
        'government': {
            'capital_stock':       cap_stk,
            'long_term_debt_neg':  None if debt is None else -debt,
            'net_financial_worth': None if debt is None else -debt,
        },
        'households': {
            'financial_wealth_proxy': hh_wealth,
        },
        'note': 'Capital stock = debt + 8× annual capex (rough accumulated-investment proxy).',
    }


# ── Assemble sfc_scenario ─────────────────────────────────────────────────────
scenario_block = {
    'methodology': {
        'sfc_identity':        'ΔL(t) = G(t) + I(t) - T(t)  [deficit increases debt]',
        'calibration':         'BAU surplus = 0.5 % of total spending; municipalities assumed legally balanced',
        'phase1_2024_2026':    'Fossil-sector employment contracts 25 %; transition capex +15 %; central-gov grant 3,000 DKK/cap pa',
        'phase2_2027_2030':    'Tax-base loss tapers linearly; grants phase out; green employment grows',
        'phase3_2031_2034':    'Permanent residual fossil loss (~10 % of Phase 1) offset by green-economy income premium',
        'wage_growth_bau':     '2 % p.a.',
        'spending_growth_bau': '1.5 % p.a.',
        'revenue_growth_bau':  '2 % p.a. (≈ wage growth)',
        'data_sources':        'DST — Financial, FiscalPolicy, Economy, LabourMarket, GreenTransition domains',
        'reference':           'Godley & Lavoie (2007) Monetary Economics; Minsky (1986) Stabilizing an Unstable Economy',
    },
}

for archetype_key, meta in ARCHETYPES.items():
    kid = meta['id']
    kd  = kommuner[kid]
    sfc = kd.get('SFCAccounts', {})
    gt  = kd.get('GreenTransition', {})
    cb  = kd.get('ClimateBaseline', {})

    scenario_block[archetype_key] = {
        'id':     kid,
        'name':   meta['name'],
        'region': kd.get('Region', ''),
        'archetype_description': (
            'High fossil-sector dependency, high debt, minimal renewable capacity — '
            'maximum transition vulnerability'
            if archetype_key == 'high_exposure'
            else 'Very high renewable intensity, lower fossil dependency — '
                 'strong green-transition position'
        ),
        'key_indicators': {
            'fossil_linked_sector_share_pct':    sc(gt.get('Fossil-linked sector share (%)')),
            'renewable_intensity_mw_per_1000':   sc(gt.get('Renewable intensity (MW/1,000)')),
            'summer_days_per_year':              sc(cb.get('Summer days per year (>25°C)')),
            'baseline_debt_per_capita':          sfc.get('L_debt_per_capita (DKK)'),
            'baseline_ops_per_capita':           sfc.get('G_ops_per_capita (DKK)'),
            'estimated_tax_revenue_per_capita':  sfc.get('T_tax_per_capita (DKK)'),
            'transition_vulnerability_index':    sfc.get('Transition_vulnerability_index'),
        },
        'years':                    [str(y) for y in YEARS],
        'scenarios':                run_scenario(kid),
        'transaction_flow_matrix':  build_tfm(kid),
        'balance_sheet_matrix':     build_bsm(kid),
    }

data['sfc_scenario'] = scenario_block

with open(OUTPUT, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, separators=(',', ':'))

print('Done.')
print(f'  SFCAccounts added to {len(kommuner)} municipalities.')
for k, v in ARCHETYPES.items():
    kid = v['id']
    sc_data = data['sfc_scenario'][k]['scenarios']
    d_bau = sc_data['bau']['debt']
    d_gt  = sc_data['green_transition']['debt']
    b_bau = sc_data['bau']['fiscal_balance']
    b_gt  = sc_data['green_transition']['fiscal_balance']
    print(f'  {k} ({v["name"]}, {kid}):')
    print(f'    BAU  debt {d_bau[0]:,} → {d_bau[-1]:,}  |  balance {b_bau[0]:,} → {b_bau[-1]:,}')
    print(f'    GT   debt {d_gt[0]:,} → {d_gt[-1]:,}  |  balance {b_gt[0]:,} → {b_gt[-1]:,}')
