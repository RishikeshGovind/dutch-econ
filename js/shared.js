const _IS_LOCAL = ['localhost', '127.0.0.1'].includes(window.location.hostname);
const PLUMBER_BASE = _IS_LOCAL
  ? 'http://127.0.0.1:8000'
  : 'https://aetherno-areastat-dk-r-api.hf.space';
const ML_BASE = _IS_LOCAL
  ? 'http://127.0.0.1:8001'
  : 'https://aetherno-areastat-dk-python-api.hf.space';

const DEFAULT_PROFILE_CATEGORIES = [
  'AgeStructure',
  'PopulationDynamics',
  'LabourMarket',
  'Economy',
  'Education',
  'Migration',
  'Ancestry',
  'Housing',
  'Safety',
  'Welfare',
  'Financial',
  'Health',
  'Businesses',
  'Vehicles'
];

const EXCLUDED_PROFILE_KEYS = [
  'Urban_rural_status',
  'Settlement_class',
  'Density_class',
  'Kommune',
  'Sognavn',
  'Region',
  'Population'
];

const SEGMENTATION_CONFIG = {
  urban_rural: {
    label_en: 'Urban-Rural',
    dataKey: 'Urban_rural_status',
    prop: '_ur',
    classes: [
      { key: 'Urban',        label_en: 'Urban',        color: '#0570b0' },
      { key: 'Intermediate', label_en: 'Intermediate', color: '#f07b20' },
      { key: 'Rural',        label_en: 'Rural',        color: '#2ca25f' },
    ]
  },
  settlement: {
    label_en: 'Settlement Size',
    dataKey: 'Settlement_class',
    prop: '_settlement',
    classes: [
      { key: 'Large City', label_en: 'Large City', color: '#6b2d8b' },
      { key: 'Small City', label_en: 'Small City', color: '#1d6fa5' },
      { key: 'Town',       label_en: 'Town',       color: '#e07520' },
      { key: 'Village',    label_en: 'Village',    color: '#3d9c57' },
    ]
  },
  density: {
    label_en: 'Population Density',
    dataKey: 'Density_class',
    prop: '_density',
    classes: [
      { key: 'Very Dense', label_en: 'Very Dense', color: '#084594' },
      { key: 'Dense',      label_en: 'Dense',      color: '#2171b5' },
      { key: 'Medium',     label_en: 'Medium',     color: '#4393c3' },
      { key: 'Sparse',     label_en: 'Sparse',     color: '#7ec8e3' },
      { key: 'Unknown',    label_en: 'Unknown',    color: '#cccccc' },
    ]
  },
};

// Single language — English
const currentLang = 'en';

const I18N = {
  'app.badge':          '◈ PhD Research Proposal',
  'app.title':          'AreaStat DK',
  'app.subtitle':       'Statistics Denmark',
  'card.header':        '◈ Select Areas',
  'card.region':        'Region',
  'card.ebene':         'Level',
  'card.clear':         'Clear',
  'card.reset':         'Reset',
  'btn.build':          'Open in AreaStat →',
  'drawer.indicators':  'Indicators ▼',
  'drawer.demographie': 'Demographics ▼',
  'drawer.economy':     'Economy ▼',
  'dom.agestructure':   'Age Structure',
  'dom.migration':      'Migration',
  'dom.housing':        'Housing',
  'dom.safety':         'Safety',
  'dom.labourmarket':   'Labour Market',
  'dom.economy':        'Economy',
  'dom.education':      'Education',
  'tab.charts':         'Charts',
  'tab.tables':         'Tables',
  'btn.excel':          '⬇ Excel',
  'btn.image':          '⬇ Image',
  'btn.typology':       'Run Typology',
  'col.indicator':      'Indicator',
  'col.selected':       'Avg Selected',
  'col.denmark':        'Denmark Avg',
};

const LABEL_EN = {
  'Under 15 years (%)':     'Under 15 years (%)',
  'Over 65 years (%)':      'Over 65 years (%)',
  'Employment rate (%)':    'Employment rate (%)',
  'Unemployment rate (%)':  'Unemployment rate (%)',
  'Out-commuter share (%)': 'Out-commuter share (%)',
  'Employees':              'Employees',
  'Avg income (DKK)':       'Avg income (DKK)',
  'Secondary education (%)':'Secondary education (%)',
  'Tertiary education (%)': 'Tertiary education (%)',
  'Foreign citizens (%)':   'Foreign citizens (%)',
  'Owner-occupied (%)':     'Owner-occupied (%)',
  'Social housing (%)':     'Social housing (%)',
  'Dwellings':              'Dwellings',
  'Crimes per 1,000':       'Crimes per 1,000',
};

const DOMAIN_EN = {
  'AgeStructure':       'Age Structure',
  'PopulationDynamics': 'Population Dynamics',
  'LabourMarket':       'Labour Market',
  'Economy':            'Economy',
  'Education':          'Education',
  'Migration':          'Migration',
  'Ancestry':           'Ancestry',
  'Housing':            'Housing',
  'Safety':             'Safety',
  'Welfare':            'Welfare',
  'Financial':          'Municipal Finances',
  'Health':             'Health',
  'Businesses':         'Businesses',
  'Vehicles':           'Vehicles',
};

const RATE_PER_1000_DOMAIN     = 'Economy';
const RATE_PER_1000_INDICATORS = ['Employees', 'Dwellings'];

function t(key) {
  return I18N[key] ?? key;
}

function tLabel(label) {
  return LABEL_EN[label] ?? label;
}

function tDomain(domain) {
  return DOMAIN_EN[domain] ?? domain;
}

function isRatePer1000Indicator(domain, indicator) {
  return domain === RATE_PER_1000_DOMAIN && RATE_PER_1000_INDICATORS.includes(indicator);
}

function displayIndicatorLabel(domain, indicator) {
  const base = tLabel(indicator);
  if (!isRatePer1000Indicator(domain, indicator)) return base;
  return `${base} per 1,000 residents`;
}

function formatIndicatorValue(domain, indicator, value) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '–';
  if (indicator.includes('(%)')) return `${value.toFixed(1)}%`;
  if (isRatePer1000Indicator(domain, indicator)) return value.toFixed(1);
  return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(2);
}

function totalPopulationForData(dataMap) {
  return Object.values(dataMap || {}).reduce((sum, zone) => {
    const pop = Number(getScalar(zone?.['Population'])) || 0;
    return sum + pop;
  }, 0);
}

function comparableDenmarkValue(domain, indicator, rawDenmarkValue) {
  if (typeof rawDenmarkValue !== 'number') return null;
  if (!isRatePer1000Indicator(domain, indicator)) return rawDenmarkValue;
  const population = Number(window.denmarkPopulation) || 0;
  return population > 0 ? (rawDenmarkValue / population) * 1000 : null;
}

// Legacy alias used by some inline calls in profile.html
function comparableAustriaValue(domain, indicator, rawVal) {
  return comparableDenmarkValue(domain, indicator, rawVal);
}

function applyLang() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    el.textContent = t(key);
  });
}

function getScalar(v) {
  if (v === null || v === undefined) return v;
  if (Array.isArray(v)) return v[0];
  if (typeof v === 'object') return Object.values(v)[0];
  return v;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
