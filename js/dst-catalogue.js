// ============================================================
// dst-catalogue.js
// Curated list of ~100 DST tables with municipal-level data,
// organised by sector. All tables are free — no API key needed.
// Source: api.statbank.dk
// ============================================================

const DST_SECTOR_ICONS = {
  'People':              '👥',
  'Labour & Income':     '💼',
  'Economy':             '📈',
  'Social Conditions':   '🏥',
  'Education':           '🎓',
  'Business':            '🏭',
  'Transport':           '🚗',
  'Culture & Leisure':   '🎭',
  'Environment':         '🌿',
};

// Each table entry:
//   id         — DST table ID
//   title      — Short display name
//   desc       — One-line description
//   unit       — Unit label shown on charts
//   areaVar    — Variable code for the area dimension (OMRÅDE, KOMKODE, etc.)
//   defaults   — Default variable values to use when auto-fetching
//                (variables not listed here are set to their first/total value)
//   timeSeries — true if the table has meaningful multi-year data

const DST_CATALOGUE = {

  // ── People ────────────────────────────────────────────────
  'People': [
    { id: 'FOLK1A',  title: 'Population (quarterly)',
      desc: 'Population at first day of quarter — by age, sex, civil status',
      unit: 'Persons', areaVar: 'OMRÅDE',
      defaults: [{ code: 'KØN', val: 'TOT' }, { code: 'ALDER', val: 'IALT' }],
      timeSeries: true },

    { id: 'FOLK1B',  title: 'Population by citizenship',
      desc: 'Population by nationality/citizenship per municipality',
      unit: 'Persons', areaVar: 'OMRÅDE',
      defaults: [{ code: 'KØN', val: 'TOT' }, { code: 'ALDER', val: 'IALT' }, { code: 'STATSB', val: 'IALT' }],
      timeSeries: true },

    { id: 'FOLK1C',  title: 'Population by ancestry',
      desc: 'Population by origin (Danish, immigrant, descendant)',
      unit: 'Persons', areaVar: 'OMRÅDE',
      defaults: [{ code: 'KØN', val: 'TOT' }, { code: 'ALDER', val: 'IALT' }],
      timeSeries: true },

    { id: 'FOLK1D',  title: 'Population by civil status',
      desc: 'Population broken down by marital status',
      unit: 'Persons', areaVar: 'OMRÅDE',
      defaults: [{ code: 'KØN', val: 'TOT' }, { code: 'ALDER', val: 'IALT' }],
      timeSeries: true },

    { id: 'BEV107',  title: 'Vital statistics (annual)',
      desc: 'Births, deaths, marriages, immigration & emigration per municipality',
      unit: 'Events', areaVar: 'OMRÅDE',
      defaults: [],
      timeSeries: true },

    { id: 'BEV22',   title: 'Vital statistics (quarterly)',
      desc: 'Quarterly births, deaths and net migration',
      unit: 'Events', areaVar: 'OMRÅDE',
      defaults: [],
      timeSeries: true },

    { id: 'INDOPH1', title: 'Immigrants (1 January)',
      desc: 'Immigrant population by country of origin',
      unit: 'Persons', areaVar: 'OMRÅDE',
      defaults: [{ code: 'KØN', val: 'MOK' }],
      timeSeries: true },

    { id: 'INDOPH3', title: 'Immigrants by background',
      desc: 'Immigrants and descendants by region of origin',
      unit: 'Persons', areaVar: 'OMRÅDE',
      defaults: [{ code: 'KØN', val: 'MOK' }],
      timeSeries: true },

    { id: 'EB4',     title: 'Population by origin background',
      desc: 'Population by Danish origin vs immigrant background',
      unit: 'Persons', areaVar: 'OMRÅDE',
      defaults: [{ code: 'KØN', val: 'MOK' }],
      timeSeries: true },

    { id: 'BEFOLK1', title: 'Population (1 January)',
      desc: 'Annual population at 1 January with age/sex breakdown',
      unit: 'Persons', areaVar: 'OMRÅDE',
      defaults: [{ code: 'KØN', val: 'TOT' }],
      timeSeries: true },

    { id: 'POSTNR1', title: 'Population by postal code',
      desc: 'Population figures at postal code level',
      unit: 'Persons', areaVar: 'POSTNR',
      defaults: [{ code: 'KØN', val: 'TOT' }],
      timeSeries: true },

    { id: 'FOLKFV',  title: 'Population projections',
      desc: 'Population forecast by municipality to 2060',
      unit: 'Persons', areaVar: 'OMRÅDE',
      defaults: [{ code: 'KØN', val: 'TOT' }, { code: 'ALDER', val: 'IALT' }],
      timeSeries: true },
  ],

  // ── Labour & Income ───────────────────────────────────────
  'Labour & Income': [
    { id: 'RAS200',   title: 'Employment & activity rates',
      desc: 'Municipal employment rate and activity rate (end November)',
      unit: 'Per cent', areaVar: 'OMRÅDE',
      defaults: [{ code: 'KØN', val: 'MOK' }],
      timeSeries: true },

    { id: 'AUL01',    title: 'Registered unemployed',
      desc: 'Gross unemployment by municipality, age and sex',
      unit: 'Full-time persons', areaVar: 'OMRÅDE',
      defaults: [{ code: 'YDELSESTYPE', val: 'TOT' }, { code: 'KØN', val: 'TOT' }, { code: 'ALDER', val: 'TOT' }, { code: 'AKASSE', val: 'TOT' }],
      timeSeries: true },

    { id: 'PEND101',  title: 'Commuting',
      desc: 'In-commuters, out-commuters and resident workers per municipality',
      unit: 'Persons', areaVar: 'OMRÅDE',
      defaults: [{ code: 'BRANCHE07', val: 'TOT' }, { code: 'KØN', val: 'M' }],
      timeSeries: true },

    { id: 'INDKP106', title: 'Disposable income per person',
      desc: 'Average disposable income per municipality (DKK)',
      unit: 'DKK', areaVar: 'OMRÅDE',
      defaults: [{ code: 'ENHED', val: '118' }, { code: 'KOEN', val: 'MOK' }, { code: 'ALDER1', val: '00' }, { code: 'INDKINTB', val: '000' }],
      timeSeries: true },

    { id: 'INDKF132', title: 'Disposable family income',
      desc: 'Average disposable income per family type (DKK)',
      unit: 'DKK', areaVar: 'OMRÅDE',
      defaults: [{ code: 'ENHED', val: '118' }],
      timeSeries: true },

    { id: 'NRS',      title: 'Households income',
      desc: 'Household income, savings and expenditure per region',
      unit: 'DKK million', areaVar: 'OMRÅDE',
      defaults: [],
      timeSeries: true },

    { id: 'LIGEAB2',  title: 'Gender equality — employment',
      desc: 'Employment rates by sex per municipality',
      unit: 'Per cent', areaVar: 'OMRÅDE',
      defaults: [],
      timeSeries: true },

    { id: 'LIGEAI2',  title: 'Gender equality index — employment',
      desc: 'Gender equality indicator for employment rate',
      unit: 'Index', areaVar: 'OMRÅDE',
      defaults: [],
      timeSeries: true },

    { id: 'RAS1',     title: 'Employment status',
      desc: 'Population by employment status (employed, unemployed, inactive)',
      unit: 'Persons', areaVar: 'OMRÅDE',
      defaults: [{ code: 'IETYPE', val: '999' }, { code: 'KØN', val: 'M' }],
      timeSeries: true },

    { id: 'AKU121K',  title: 'Labour force status (%)',
      desc: 'Labour force participation, employment and unemployment rates',
      unit: 'Per cent', areaVar: 'REGION',
      defaults: [{ code: 'KØN', val: 'TOT' }],
      timeSeries: true },

    { id: 'KAS200',   title: 'Average employment rates',
      desc: 'Annual average employment and activity rates',
      unit: 'Per cent', areaVar: 'OMRÅDE',
      defaults: [{ code: 'KØN', val: 'MOK' }],
      timeSeries: true },

    { id: 'RAS201',   title: 'Working-age population',
      desc: 'Population aged 15–74 by labour force status per municipality',
      unit: 'Persons', areaVar: 'OMRÅDE',
      defaults: [{ code: 'KØN', val: 'MOK' }],
      timeSeries: true },
  ],

  // ── Economy ───────────────────────────────────────────────
  'Economy': [
    { id: 'NGLK',    title: 'Municipal finances (key figures)',
      desc: 'Tax revenue, expenditure, debt and surplus per municipality',
      unit: 'DKK 1,000', areaVar: 'KOMKODE',
      defaults: [],
      timeSeries: true },

    { id: 'REGK11',  title: 'Municipal accounts',
      desc: 'Full municipal budget by main account (expenditure & revenue)',
      unit: 'DKK 1,000', areaVar: 'KOMKODE',
      defaults: [],
      timeSeries: true },

    { id: 'NRHP',    title: 'Regional GDP & production',
      desc: 'Gross value added and GDP by municipality/region',
      unit: 'DKK million', areaVar: 'OMRÅDE',
      defaults: [],
      timeSeries: true },

    { id: 'NRHB',    title: 'Regional population (economic)',
      desc: 'Population used in national accounts calculations',
      unit: 'Persons', areaVar: 'OMRÅDE',
      defaults: [],
      timeSeries: true },

    { id: 'NRBB10',  title: 'Employment by industry (regional)',
      desc: 'Regional employment broken down by 10 industry groups',
      unit: 'Persons', areaVar: 'OMRÅDE',
      defaults: [],
      timeSeries: true },

    { id: 'NRBP10',  title: 'Production by industry (regional)',
      desc: 'Regional production and income by industry group',
      unit: 'DKK million', areaVar: 'OMRÅDE',
      defaults: [],
      timeSeries: true },

    { id: 'NRBI10',  title: 'Gross fixed capital formation',
      desc: 'Regional investment by industry',
      unit: 'DKK million', areaVar: 'OMRÅDE',
      defaults: [],
      timeSeries: true },

    { id: 'ARE207',  title: 'Land area (km²)',
      desc: 'Total land area of each municipality in square kilometres',
      unit: 'km²', areaVar: 'OMRÅDE',
      defaults: [],
      timeSeries: false },

    { id: 'GF14',    title: 'General enterprise statistics',
      desc: 'Employment and turnover of enterprises by municipality',
      unit: 'Number', areaVar: 'REGION',
      defaults: [],
      timeSeries: true },
  ],

  // ── Social Conditions ─────────────────────────────────────
  'Social Conditions': [
    { id: 'AUK01',  title: 'Benefit recipients (quarterly)',
      desc: 'Persons receiving unemployment benefits, sick pay, disability etc.',
      unit: 'Persons', areaVar: 'OMRÅDE',
      defaults: [{ code: 'KØN', val: 'TOT' }],
      timeSeries: true },

    { id: 'AUK03',  title: 'Benefit recipients (detailed)',
      desc: 'Public benefit recipients by type and municipality',
      unit: 'Persons', areaVar: 'OMRÅDE',
      defaults: [{ code: 'KØN', val: 'TOT' }],
      timeSeries: true },

    { id: 'AUH01',  title: 'Not in ordinary employment',
      desc: 'Persons outside ordinary employment by benefit type',
      unit: 'Persons', areaVar: 'OMRÅDE',
      defaults: [{ code: 'KØN', val: 'TOT' }],
      timeSeries: true },

    { id: 'AUH03',  title: 'Public benefit recipients (annual)',
      desc: 'Annual count of persons receiving public transfers',
      unit: 'Persons', areaVar: 'OMRÅDE',
      defaults: [{ code: 'KØN', val: 'TOT' }],
      timeSeries: true },

    { id: 'BOL101', title: 'Dwellings by ownership',
      desc: 'Occupied dwellings by ownership type (private, social, public)',
      unit: 'Dwellings', areaVar: 'OMRÅDE',
      defaults: [{ code: 'BEBO', val: '1000' }],
      timeSeries: true },

    { id: 'STRAF11',title: 'Reported offences',
      desc: 'Total reported crimes per municipality by type',
      unit: 'Number', areaVar: 'OMRÅDE',
      defaults: [{ code: 'OVERTRÆD', val: 'TOT' }],
      timeSeries: true },

    { id: 'KY034',  title: 'Cash benefits',
      desc: 'Persons receiving cash benefits (kontanthjælp)',
      unit: 'Persons', areaVar: 'OMRÅDE',
      defaults: [{ code: 'KØN', val: 'TOT' }],
      timeSeries: true },

    { id: 'KY035',  title: 'Cash benefits (full-time)',
      desc: 'Full-time equivalents on cash benefits',
      unit: 'Full-time persons', areaVar: 'OMRÅDE',
      defaults: [{ code: 'KØN', val: 'TOT' }],
      timeSeries: true },

    { id: 'KY051',  title: 'Special benefits',
      desc: 'Recipients of special social benefits per municipality',
      unit: 'Persons', areaVar: 'OMRÅDE',
      defaults: [{ code: 'KØN', val: 'TOT' }],
      timeSeries: true },

    { id: 'AUH04',  title: 'Activation measures',
      desc: 'Persons in activation/labour market programmes',
      unit: 'Persons', areaVar: 'OMRÅDE',
      defaults: [{ code: 'KØN', val: 'TOT' }],
      timeSeries: true },
  ],

  // ── Education ─────────────────────────────────────────────
  'Education': [
    { id: 'HFUDD11',  title: 'Educational attainment (15–69)',
      desc: 'Highest education level of population aged 15–69',
      unit: 'Persons', areaVar: 'BOPOMR',
      defaults: [{ code: 'KØN', val: 'TOT' }, { code: 'HERKOMST', val: 'TOT' }, { code: 'ALDER', val: 'TOT' }, { code: 'HFUDD', val: 'TOT' }],
      timeSeries: true },

    { id: 'HFUDD16',  title: 'Educational attainment (variant)',
      desc: 'Educational attainment with additional breakdowns',
      unit: 'Persons', areaVar: 'BOPOMR',
      defaults: [{ code: 'KØN', val: 'TOT' }, { code: 'ALDER', val: 'TOT' }],
      timeSeries: true },

    { id: 'HFUDD21',  title: 'Educational attainment (15–29)',
      desc: 'Education level among young adults aged 15–29',
      unit: 'Persons', areaVar: 'BOPOMR',
      defaults: [{ code: 'KØN', val: 'TOT' }],
      timeSeries: true },

    { id: 'UDDAKT10', title: 'Educational activity',
      desc: 'Students enrolled by level of education per municipality',
      unit: 'Persons', areaVar: 'BOPKODE',
      defaults: [{ code: 'KØN', val: 'TOT' }],
      timeSeries: true },

    { id: 'UDDAKT20', title: 'Primary school activity',
      desc: 'Students in primary and lower secondary school',
      unit: 'Persons', areaVar: 'BOPKODE',
      defaults: [{ code: 'KØN', val: 'TOT' }],
      timeSeries: true },

    { id: 'UDDAKT30', title: 'Upper secondary activity',
      desc: 'Students in upper secondary education',
      unit: 'Persons', areaVar: 'BOPKODE',
      defaults: [{ code: 'KØN', val: 'TOT' }],
      timeSeries: true },

    { id: 'KVOTIEN',  title: 'Class quotients (primary school)',
      desc: 'Average class size in primary schools per municipality',
      unit: 'Students per class', areaVar: 'KOMKODE',
      defaults: [],
      timeSeries: true },

    { id: 'LIGEUB1',  title: 'Gender equality — education',
      desc: 'Educational attainment by sex (gender equality focus)',
      unit: 'Per cent', areaVar: 'BOPOMR',
      defaults: [],
      timeSeries: true },

    { id: 'FORLOB10', title: 'Education progression',
      desc: 'Transition rates from primary school to further education',
      unit: 'Per cent', areaVar: 'BOPKODE',
      defaults: [],
      timeSeries: true },

    { id: 'UDDALL10', title: 'Educational activity (all levels)',
      desc: 'All enrolled students by education type per municipality',
      unit: 'Persons', areaVar: 'BOPKODE',
      defaults: [{ code: 'KØN', val: 'TOT' }],
      timeSeries: true },
  ],

  // ── Business ──────────────────────────────────────────────
  'Business': [
    { id: 'ERHV2',   title: 'Workplaces & jobs',
      desc: 'Number of workplaces and full-time jobs by municipality',
      unit: 'Number', areaVar: 'OMRÅDE',
      defaults: [{ code: 'BRANCHE07', val: 'TOT' }],
      timeSeries: true },

    { id: 'ERHV5',   title: 'Workplaces',
      desc: 'Local workplaces by industry and municipality',
      unit: 'Workplaces', areaVar: 'OMRÅDE',
      defaults: [{ code: 'BRANCHE07', val: 'TOT' }],
      timeSeries: true },

    { id: 'ERHV6',   title: 'Employees at workplaces',
      desc: 'Employees at local workplaces by industry size class',
      unit: 'Persons', areaVar: 'OMRÅDE',
      defaults: [{ code: 'BRANCHE0710', val: 'TOT' }],
      timeSeries: true },

    { id: 'DEMO14',  title: 'Business demography',
      desc: 'Enterprise births, deaths and survival rates per municipality',
      unit: 'Number', areaVar: 'REGION',
      defaults: [],
      timeSeries: true },

    { id: 'GF14',    title: 'Enterprise statistics',
      desc: 'Number, employment and turnover of active enterprises',
      unit: 'Number', areaVar: 'REGION',
      defaults: [],
      timeSeries: true },

    { id: 'LS02',    title: 'Job vacancies (annual)',
      desc: 'Number of job vacancies by industry and municipality',
      unit: 'Vacancies', areaVar: 'REGION',
      defaults: [],
      timeSeries: true },

    { id: 'REGN80',  title: 'Accounts statistics',
      desc: 'Revenue, profit and employment from enterprise accounts',
      unit: 'DKK million', areaVar: 'REGION',
      defaults: [],
      timeSeries: true },

    { id: 'JOEK2',   title: 'Agricultural accounts',
      desc: 'Economic results of agricultural holdings per region',
      unit: 'DKK 1,000', areaVar: 'REGION',
      defaults: [],
      timeSeries: true },

    { id: 'FDEMO4',  title: 'Business demography (preliminary)',
      desc: 'Preliminary enterprise births and deaths figures',
      unit: 'Number', areaVar: 'REGION',
      defaults: [],
      timeSeries: false },
  ],

  // ── Transport ─────────────────────────────────────────────
  'Transport': [
    { id: 'BIL707',  title: 'Vehicle stock (1 January)',
      desc: 'Total registered motor vehicles per municipality',
      unit: 'Vehicles', areaVar: 'KOMKODE',
      defaults: [],
      timeSeries: true },

    { id: 'BIL710',  title: 'Passenger cars (1 January)',
      desc: 'Passenger car stock per municipality',
      unit: 'Vehicles', areaVar: 'KOMKODE',
      defaults: [],
      timeSeries: true },

    { id: 'BIL53',   title: 'New vehicle registrations',
      desc: 'Monthly new registrations of motor vehicles per municipality',
      unit: 'Vehicles', areaVar: 'KOMKODE',
      defaults: [],
      timeSeries: true },

    { id: 'BIL54',   title: 'Vehicle stock (monthly)',
      desc: 'Monthly stock of all registered vehicles',
      unit: 'Vehicles', areaVar: 'KOMKODE',
      defaults: [],
      timeSeries: true },

    { id: 'BIL600',  title: 'Family vehicle purchases',
      desc: 'Vehicles purchased by households per municipality',
      unit: 'Vehicles', areaVar: 'KOMKODE',
      defaults: [],
      timeSeries: true },

    { id: 'BIL800',  title: 'Vehicle disposals',
      desc: 'Vehicles scrapped or sold by household municipality',
      unit: 'Vehicles', areaVar: 'KOMKODE',
      defaults: [],
      timeSeries: true },

    { id: 'BIL907',  title: 'Trailer stock',
      desc: 'Registered trailers per municipality',
      unit: 'Trailers', areaVar: 'KOMKODE',
      defaults: [],
      timeSeries: true },
  ],

  // ── Culture & Leisure ─────────────────────────────────────
  'Culture & Leisure': [
    { id: 'BIB1',     title: 'Public libraries (key figures)',
      desc: 'Loans, visits, staff and budget of public libraries',
      unit: 'Number', areaVar: 'KOMKODE',
      defaults: [],
      timeSeries: true },

    { id: 'BIB2B',    title: 'Libraries — activities',
      desc: 'Library activities, events and digital services',
      unit: 'Number', areaVar: 'KOMKODE',
      defaults: [],
      timeSeries: true },

    { id: 'BIB3',     title: 'Library materials (physical)',
      desc: 'Physical books, CDs and other materials in libraries',
      unit: 'Items', areaVar: 'KOMKODE',
      defaults: [],
      timeSeries: true },

    { id: 'BIB6',     title: 'Library economy',
      desc: 'Library expenditure and funding per municipality',
      unit: 'DKK 1,000', areaVar: 'KOMKODE',
      defaults: [],
      timeSeries: true },

    { id: 'MUS3',     title: 'Museum activity',
      desc: 'Visitors, staff and exhibitions at museum sites',
      unit: 'Visitors', areaVar: 'KOMKODE',
      defaults: [],
      timeSeries: true },

    { id: 'KFRED1',   title: 'Protected buildings',
      desc: 'Listed/protected buildings per municipality',
      unit: 'Buildings', areaVar: 'KOMKODE',
      defaults: [],
      timeSeries: true },

    { id: 'KFRED2',   title: 'Protected ancient monuments',
      desc: 'Scheduled ancient monuments per municipality',
      unit: 'Monuments', areaVar: 'KOMKODE',
      defaults: [],
      timeSeries: true },

    { id: 'ARKIV02B', title: 'City & local archives',
      desc: 'Activity and staffing of municipal archives',
      unit: 'Number', areaVar: 'KOMKODE',
      defaults: [],
      timeSeries: true },
  ],

  // ── Environment & Energy ──────────────────────────────────
  'Environment': [
    { id: 'AREALDK2', title: 'Land use',
      desc: 'Area by land use category (agriculture, forest, urban) per municipality',
      unit: 'km²', areaVar: 'REGION',
      defaults: [],
      timeSeries: true },

    { id: 'ARE207',   title: 'Municipal area (km²)',
      desc: 'Total area of each municipality in square kilometres',
      unit: 'km²', areaVar: 'OMRÅDE',
      defaults: [],
      timeSeries: false },

    { id: 'VANDIND',  title: 'Water abstraction',
      desc: 'Groundwater and surface water abstraction per municipality',
      unit: '1,000 m³', areaVar: 'REGION',
      defaults: [],
      timeSeries: true },

    { id: 'VANDUD',   title: 'Wastewater discharge',
      desc: 'Discharge of wastewater by type per municipality',
      unit: '1,000 m³', areaVar: 'REGION',
      defaults: [],
      timeSeries: true },

    { id: 'JORD1',    title: 'Farm accounts (profit & loss)',
      desc: 'Profit and loss accounts for all farms per region',
      unit: 'DKK 1,000', areaVar: 'REGION',
      defaults: [],
      timeSeries: true },

    { id: 'JORD6',    title: 'Farm key indicators',
      desc: 'Key economic indicators for agricultural holdings',
      unit: 'DKK 1,000', areaVar: 'REGION',
      defaults: [],
      timeSeries: true },

    { id: 'AREALAN1', title: 'Land use (detailed)',
      desc: 'Detailed land use breakdown including green/natural areas',
      unit: 'km²', areaVar: 'REGION',
      defaults: [],
      timeSeries: false },
  ],
};

// Flat lookup: tableId → { sector, ...entry }
const DST_TABLE_INDEX = {};
for (const [sector, tables] of Object.entries(DST_CATALOGUE)) {
  for (const tbl of tables) {
    DST_TABLE_INDEX[tbl.id] = { ...tbl, sector };
  }
}

// Returns list of all sector names in display order
function getDSTSectors() {
  return Object.keys(DST_CATALOGUE);
}

// Returns tables for a given sector
function getDSTTablesForSector(sector) {
  return DST_CATALOGUE[sector] || [];
}
