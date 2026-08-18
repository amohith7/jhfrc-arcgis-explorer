// dashboard/js/dashboard.js
// JHFRC Regional Explorer — extracted from dashboard/index.html
// during Brief 3 Phase H1 (module split).
//
// This is currently one file for the extract step. The next PR
// (H1b) will split it into state/format/data/csv/trends/map/
// views/ui/main modules with explicit dependency ordering.
//
// Everything runs in the global scope so referencing between
// what were previously sibling `<script>` code paths continues
// to work unchanged.

// ─────────────────────────────────────────────────────────────────────
    // Configuration
    // 61 indicators mirrored from build_arcgis_layer.py HEADLINE_INDICATORS.
    // Fields per entry:
    //   id            — column name on the Feature Layer
    //   label         — human-readable name shown throughout UI
    //   domain        — dropdown group
    //   higherIsWorse — true/false/null; drives shading + best-of picking
    //   unit          — 'percent' | 'currency' | 'index' | 'years' | 'count'
    //   decimals      — decimal places for the value + delta formatters
    const INDICATORS = [
      // Economic
      { id: 'pov_below',   label: 'Below Poverty Line (%)',                  domain: 'Economic',      higherIsWorse: true,  unit: 'percent',  decimals: 1 },
      { id: 'mhi',         label: 'Median Household Income ($)',             domain: 'Economic',      higherIsWorse: false, unit: 'currency', decimals: 0 },
      { id: 'mpci',        label: 'Mean Per Capita Income ($)',              domain: 'Economic',      higherIsWorse: false, unit: 'currency', decimals: 0 },
      { id: 'gini',        label: 'Gini Index (income inequality)',          domain: 'Economic',      higherIsWorse: true,  unit: 'index',    decimals: 3 },
      { id: 'emp_adults',  label: 'Employed Adults (%)',                     domain: 'Economic',      higherIsWorse: false, unit: 'percent',  decimals: 1 },
      { id: 'not_labor',   label: 'Not in Labor Force (%)',                  domain: 'Economic',      higherIsWorse: true,  unit: 'percent',  decimals: 1 },
      { id: 'hh_snap',     label: 'Households Receiving SNAP (%)',           domain: 'Economic',      higherIsWorse: true,  unit: 'percent',  decimals: 1 },
      { id: 'hh_pubasst',  label: 'Households Receiving Public Assistance (%)', domain: 'Economic',   higherIsWorse: true,  unit: 'percent',  decimals: 1 },
      // Education
      { id: 'edu_lths',    label: 'Less than High School Education (%)',     domain: 'Education',     higherIsWorse: true,  unit: 'percent',  decimals: 1 },
      { id: 'edu_posths',  label: 'Any Post-High School Education (%)',      domain: 'Education',     higherIsWorse: false, unit: 'percent',  decimals: 1 },
      { id: 'edu_assoc',   label: "Associate's Degree (%)",                  domain: 'Education',     higherIsWorse: false, unit: 'percent',  decimals: 1 },
      { id: 'edu_ba',      label: "Bachelor's Degree (%)",                   domain: 'Education',     higherIsWorse: false, unit: 'percent',  decimals: 1 },
      { id: 'edu_grad',    label: 'Graduate / Professional Degree (%)',      domain: 'Education',     higherIsWorse: false, unit: 'percent',  decimals: 1 },
      { id: 'youth_dis',   label: 'Youth Disconnection — Teens 16-19 (%)',   domain: 'Education',     higherIsWorse: true,  unit: 'percent',  decimals: 1 },
      // Healthcare — coverage
      { id: 'no_insur',    label: 'Uninsured, Ages 18-64 (%)',               domain: 'Healthcare',    higherIsWorse: true,  unit: 'percent',  decimals: 1 },
      { id: 'private_ins', label: 'Private Insurance (All Ages) (%)',        domain: 'Healthcare',    higherIsWorse: false, unit: 'percent',  decimals: 1 },
      { id: 'medicaid',    label: 'Medicaid Coverage (%)',                   domain: 'Healthcare',    higherIsWorse: null,  unit: 'percent',  decimals: 1 },
      { id: 'any_disab',   label: 'Any Disability (%)',                      domain: 'Healthcare',    higherIsWorse: true,  unit: 'percent',  decimals: 1 },
      // Healthcare — conditions
      { id: 'hh_diab',     label: 'Diabetes (%)',                            domain: 'Healthcare',    higherIsWorse: true,  unit: 'percent',  decimals: 1 },
      { id: 'hh_asthma',   label: 'Asthma (%)',                              domain: 'Healthcare',    higherIsWorse: true,  unit: 'percent',  decimals: 1 },
      { id: 'hh_heart',    label: 'Coronary Heart Disease (%)',              domain: 'Healthcare',    higherIsWorse: true,  unit: 'percent',  decimals: 1 },
      { id: 'hh_bp',       label: 'High Blood Pressure (%)',                 domain: 'Healthcare',    higherIsWorse: true,  unit: 'percent',  decimals: 1 },
      { id: 'hh_bpmed',    label: 'Taking Blood Pressure Medication (%)',    domain: 'Healthcare',    higherIsWorse: null,  unit: 'percent',  decimals: 1 },
      { id: 'hh_chol',     label: 'High Cholesterol (%)',                    domain: 'Healthcare',    higherIsWorse: true,  unit: 'percent',  decimals: 1 },
      { id: 'hh_arthr',    label: 'Arthritis (%)',                           domain: 'Healthcare',    higherIsWorse: true,  unit: 'percent',  decimals: 1 },
      { id: 'hh_copd',     label: 'COPD (%)',                                domain: 'Healthcare',    higherIsWorse: true,  unit: 'percent',  decimals: 1 },
      { id: 'hh_stroke',   label: 'Stroke (%)',                              domain: 'Healthcare',    higherIsWorse: true,  unit: 'percent',  decimals: 1 },
      // Healthcare — self-reported + behaviors
      { id: 'ph_poor14',   label: 'Poor Physical Health ≥14 Days (%)',       domain: 'Healthcare',    higherIsWorse: true,  unit: 'percent',  decimals: 1 },
      { id: 'mh_poor14',   label: 'Poor Mental Health ≥14 Days (%)',         domain: 'Healthcare',    higherIsWorse: true,  unit: 'percent',  decimals: 1 },
      { id: 'fair_hlth',   label: 'Fair or Poor Self-Reported Health (%)',   domain: 'Healthcare',    higherIsWorse: true,  unit: 'percent',  decimals: 1 },
      { id: 'smoke',       label: 'Smoking (%)',                             domain: 'Healthcare',    higherIsWorse: true,  unit: 'percent',  decimals: 1 },
      { id: 'binge',       label: 'Binge Drinking (%)',                      domain: 'Healthcare',    higherIsWorse: true,  unit: 'percent',  decimals: 1 },
      { id: 'no_activ',    label: 'No Leisure-Time Physical Activity (%)',   domain: 'Healthcare',    higherIsWorse: true,  unit: 'percent',  decimals: 1 },
      { id: 'obesity',     label: 'Obesity (%)',                             domain: 'Healthcare',    higherIsWorse: true,  unit: 'percent',  decimals: 1 },
      { id: 'sleep_lt7',   label: 'Sleeping Less than 7 Hours (%)',          domain: 'Healthcare',    higherIsWorse: true,  unit: 'percent',  decimals: 1 },
      // Housing
      { id: 'med_rent',    label: 'Median Gross Rent ($)',                   domain: 'Housing',       higherIsWorse: null,  unit: 'currency', decimals: 0 },
      { id: 'med_home',    label: 'Median Home Value ($)',                   domain: 'Housing',       higherIsWorse: null,  unit: 'currency', decimals: 0 },
      { id: 'owner_occ',   label: 'Owner-Occupied Households (%)',           domain: 'Housing',       higherIsWorse: null,  unit: 'percent',  decimals: 1 },
      { id: 'renter_occ',  label: 'Renter-Occupied Households (%)',          domain: 'Housing',       higherIsWorse: null,  unit: 'percent',  decimals: 1 },
      { id: 'vacant',      label: 'Vacant Housing Units (%)',                domain: 'Housing',       higherIsWorse: true,  unit: 'percent',  decimals: 1 },
      { id: 'cost_owner',  label: 'Owners Paying ≥30% of Income (%)',        domain: 'Housing',       higherIsWorse: true,  unit: 'percent',  decimals: 1 },
      { id: 'cost_rent',   label: 'Renters Paying ≥30% of Income (%)',       domain: 'Housing',       higherIsWorse: true,  unit: 'percent',  decimals: 1 },
      { id: 'housing_old', label: 'Housing Built Before 1979 (%)',           domain: 'Housing',       higherIsWorse: null,  unit: 'percent',  decimals: 1 },
      // Digital & Transportation
      { id: 'bb_access',   label: 'Households with Broadband Access (%)',    domain: 'Digital & Transportation', higherIsWorse: false, unit: 'percent', decimals: 1 },
      { id: 'no_intnet',   label: 'Households without Internet Access (%)',  domain: 'Digital & Transportation', higherIsWorse: true,  unit: 'percent', decimals: 1 },
      { id: 'no_veh',      label: 'Households without a Vehicle (%)',        domain: 'Digital & Transportation', higherIsWorse: true,  unit: 'percent', decimals: 1 },
      { id: 'transit',     label: 'Public Transit Commuters (%)',            domain: 'Digital & Transportation', higherIsWorse: false, unit: 'percent', decimals: 1 },
      { id: 'walk',        label: 'Workers Walking to Work (%)',             domain: 'Digital & Transportation', higherIsWorse: null,  unit: 'percent', decimals: 1 },
      // Social
      { id: 'age_65p',     label: 'Population Age 65+ (%)',                  domain: 'Social',        higherIsWorse: null,  unit: 'percent',  decimals: 1 },
      { id: 'age_18_64',   label: 'Population Age 18-64 (%)',                domain: 'Social',        higherIsWorse: null,  unit: 'percent',  decimals: 1 },
      { id: 'med_age',     label: 'Median Age',                              domain: 'Social',        higherIsWorse: null,  unit: 'years',    decimals: 1 },
      { id: 'single_p',    label: 'Single-Parent Families (%)',              domain: 'Social',        higherIsWorse: true,  unit: 'percent',  decimals: 1 },
      { id: 'live_alon_65',label: 'Age 65+ Living Alone (%)',                domain: 'Social',        higherIsWorse: null,  unit: 'percent',  decimals: 1 },
      { id: 'hh_size',     label: 'Average Household Size',                  domain: 'Social',        higherIsWorse: null,  unit: 'count',    decimals: 2 },
      { id: 'married',     label: 'Married (%)',                             domain: 'Social',        higherIsWorse: null,  unit: 'percent',  decimals: 1 },
      { id: 'hisp',        label: 'Hispanic (%)',                            domain: 'Race, Ethnicity & Language', higherIsWorse: null, unit: 'percent', decimals: 1 },
      { id: 'black',       label: 'Black / African American (%)',            domain: 'Race, Ethnicity & Language', higherIsWorse: null, unit: 'percent', decimals: 1 },
      { id: 'white',       label: 'White (%)',                               domain: 'Race, Ethnicity & Language', higherIsWorse: null, unit: 'percent', decimals: 1 },
      { id: 'asian',       label: 'Asian (%)',                               domain: 'Race, Ethnicity & Language', higherIsWorse: null, unit: 'percent', decimals: 1 },
      { id: 'foreign_born', label: 'Foreign Born Population (%)',            domain: 'Race, Ethnicity & Language', higherIsWorse: null, unit: 'percent', decimals: 1 },
      { id: 'lang_span',   label: 'Spanish Speakers, Age 5+ (%)',            domain: 'Race, Ethnicity & Language', higherIsWorse: null, unit: 'percent', decimals: 1 },
    ];

    // Correlation matrix — 12 broad-signal indicators covering the SDoH
    // domains. This is the aspirational full list; the actual matrix
    // uses corrIndicators() which filters to what the layer actually
    // publishes and falls back to a domain-spanning subset of the live
    // 21 when many of the aspirational picks aren't published yet.
    const CORR_INDICATORS_TARGET = [
      'pov_below','mhi','edu_ba','no_insur','obesity','hh_diab',
      'ph_poor14','bb_access','no_veh','youth_dis','cost_rent','single_p'
    ];
    const CORR_INDICATORS_FALLBACK = [
      'pov_below','mhi','mpci','emp_adults','edu_ba','edu_posths',
      'hh_snap','hh_diab','obesity','smoke','vacant','med_rent'
    ];
    function corrIndicators() {
      const present = state.presentFields || new Set();
      const fromTarget = CORR_INDICATORS_TARGET.filter(id => present.has(id));
      // If at least three-quarters of the target list is published, use
      // it. Otherwise use the fallback (also filtered to what's live).
      let list;
      if (fromTarget.length >= Math.ceil(CORR_INDICATORS_TARGET.length * 0.75)) {
        list = fromTarget;
      } else {
        const fromFallback = CORR_INDICATORS_FALLBACK.filter(id => present.has(id));
        list = fromFallback.length >= 3 ? fromFallback : fromTarget;
      }
      // Also drop anything that has no non-null value for the current
      // county selection — matches the dropdown / Compare behaviour.
      if (_availableIds && _availableIds.size > 0) {
        list = list.filter(id => _availableIds.has(id));
      }
      return list;
    }

    const LAYER_URL = 'https://services.arcgis.com/UnTXoPXBYERF0OH6/arcgis/rest/services/jhfrc_census_tracts_v3/FeatureServer/0';

    const state = {
      features: [], counties: new Set(),
      indA: 'pov_below', indB: 'edu_ba',
      charts: {}, mapView: null, layer: null,
    };

    // ─── URL state (Brief 2 C5) ─────────────────────────────────────
    // Serialize the picked indicators + county filter into location.hash
    // so a shared link reproduces the view. Format:
    //   #a=<indA>&b=<indB>&c=<county1>,<county2>,...
    // Absent keys leave the current state alone (partial links are OK).
    function readUrlState() {
      const raw = (location.hash || '').replace(/^#/, '');
      if (!raw) return {};
      const params = new URLSearchParams(raw);
      const out = {};
      const a = params.get('a'); if (a) out.indA = a;
      const b = params.get('b'); if (b) out.indB = b;
      const c = params.get('c'); if (c) out.counties = c.split(',').map(s => decodeURIComponent(s)).filter(Boolean);
      return out;
    }
    function writeUrlState() {
      try {
        const cs = [...selectedCounties()];
        const p = new URLSearchParams();
        p.set('a', state.indA);
        p.set('b', state.indB);
        // Only write the counties list when it's a real subset. All-
        // selected = omit key so a copy-paste link doesn't lock the
        // reader into "all 11 counties" if we later change the pilot.
        if (cs.length > 0 && cs.length < state.counties.size) {
          p.set('c', cs.map(encodeURIComponent).join(','));
        }
        const next = '#' + p.toString();
        // replaceState so the back button doesn't cycle through every
        // filter toggle.
        if (location.hash !== next) history.replaceState(null, '', next);
      } catch (_) { /* URL state is a nice-to-have; never break the app */ }
    }
    function applyUrlState(u) {
      if (u.indA) state.indA = u.indA;
      if (u.indB) state.indB = u.indB;
      if (u.counties) {
        const wanted = new Set(u.counties);
        document.querySelectorAll('#countyList input').forEach(inp => {
          inp.checked = wanted.has(inp.value);
        });
      }
    }

    // ─── CSV export (Brief 2 C5, extended Brief 3 D4) ───────────────
    // Build a CSV blob from a header row + rows-of-arrays payload and
    // trigger a download. Numeric values pass through unquoted so
    // Excel and pandas parse them as numbers, not strings. Optional
    // preamble (array of "# ..." comment lines) carries provenance
    // — layer URL, vintages, retrieval date, citation — so an
    // analyst reading the file downstream can still cite it. pandas
    // reads these via `pd.read_csv(..., comment='#')`; Excel ignores
    // them if you check "Treat consecutive delimiters as one" and
    // starts at the first non-# row.
    function downloadCsv(filename, header, rows, preamble) {
      const q = v => {
        if (v == null) return '';
        // Preserve numeric type — number → unquoted numeric literal.
        if (typeof v === 'number') return isFinite(v) ? String(v) : '';
        const s = String(v);
        // Only quote when needed — commas, quotes, newlines, or leading
        // spaces. Escape embedded quotes by doubling.
        return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
      };
      const lines = [];
      if (Array.isArray(preamble)) lines.push(...preamble);
      lines.push([header, ...rows].map(r => r.map(q).join(',')).join('\r\n'));
      const body = lines.join('\r\n');
      const blob = new Blob(['﻿' + body], {type: 'text/csv;charset=utf-8'});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = filename;
      document.body.appendChild(a); a.click();
      setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 0);
    }

    // Indicator lookup used by fmt() when an id string is passed.
    const INDICATORS_BY_ID = Object.fromEntries(INDICATORS.map(i => [i.id, i]));

    // Source-of-truth tags. PLACES = CDC's model-based small-area
    // estimates (BRFSS + demographics). CDC advises AGAINST comparing
    // PLACES releases across years to derive change over time — the
    // model is periodically re-specified and the underlying inputs
    // differ, so year-over-year "movement" in a tract's PLACES value
    // is largely model drift, not actual epidemiological change.
    // Everything else is ACS-derived and does support 5-year change.
    // Brief 2 C2. Reference:
    //   https://www.cdc.gov/places/methodology/index.html
    // Source + trend-eligibility now come from data/dictionary.json
    // (Brief 3 Amendment B10 + B6). Fallback to hardcoded PLACES set
    // when dictionary fetch fails so the dashboard still boots.
    const PLACES_INDICATOR_IDS = new Set([
      'hh_diab','hh_asthma','hh_heart','hh_bp','hh_bpmed','hh_chol',
      'hh_arthr','hh_copd','hh_stroke','ph_poor14','mh_poor14',
      'fair_hlth','smoke','binge','no_activ','obesity','sleep_lt7',
    ]);
    for (const ind of INDICATORS) {
      ind.source = PLACES_INDICATOR_IDS.has(ind.id) ? 'PLACES' : 'ACS';
      // Sensible defaults; dictionary.json overrides these at boot.
      ind.hasTrend = !PLACES_INDICATOR_IDS.has(ind.id) && ind.id !== 'any_disab';
      ind.compositeEligible = !PLACES_INDICATOR_IDS.has(ind.id)
        && ind.domain !== 'Race, Ethnicity & Language';
    }

    // ─── Dictionary loader (Brief 3 E5 + F1) ────────────────────────
    // Merges data/dictionary.json into the runtime INDICATORS metadata.
    // Populates the F1 info-icon popover, F2 benchmark strip, and gates
    // hasTrend / compositeEligible from a single source of truth.
    async function loadIndicatorDictionary() {
      try {
        const r = await fetch('../data/dictionary.json', {cache: 'no-cache'});
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const d = await r.json();
        state.dictionary = d;
        for (const [id, meta] of Object.entries(d.indicators || {})) {
          const ind = INDICATORS_BY_ID[id];
          if (!ind) continue;
          if (meta.source) ind.source = meta.source;
          if (typeof meta.hasTrend === 'boolean') ind.hasTrend = meta.hasTrend;
          if (typeof meta.compositeEligible === 'boolean') ind.compositeEligible = meta.compositeEligible;
          if (meta.universe) ind.universe = meta.universe;
          if (meta.why_it_matters) ind.why_it_matters = meta.why_it_matters;
          if (meta.limitation) ind.limitation = meta.limitation;
          if (meta.table) ind.table = meta.table;
          if (meta.measure_id) ind.measure_id = meta.measure_id;
          if (typeof meta.us_avg === 'number') ind.us_avg = meta.us_avg;
          if (typeof meta.tn_avg === 'number') ind.tn_avg = meta.tn_avg;
        }
        return true;
      } catch (e) {
        console.warn('dictionary.json load failed — falling back to code defaults', e);
        return false;
      }
    }

    function indicatorSupportsDelta(id) {
      // Two gates: layer publishes _d5 AND the indicator's metadata
      // says the value moves across releases (ACS windows do; PLACES
      // model releases don't; any_disab has no delta published).
      // Brief 3 Amendment B10.
      const ind = INDICATORS_BY_ID[id];
      if (ind && ind.hasTrend === false) return false;
      if (state.publishedDeltaIds && !state.publishedDeltaIds.has(id)) return false;
      return true;
    }
    function deltaUnavailableReason(id) {
      const ind = INDICATORS_BY_ID[id];
      if (ind && ind.source === 'PLACES') {
        return 'CDC PLACES model-based estimates are not comparable across releases (model re-specification). 5-year change is intentionally suppressed.';
      }
      return '5-year change not published for this indicator on the layer.';
    }

    // Format a value with the indicator's unit + decimal-place rules.
    // `ind` can be an indicator object, an indicator id, or omitted
    // (fallback for county names / chart tick labels that need a
    // generic thousands-separated number).
    function fmt(v, ind) {
      if (v == null || (typeof v === 'number' && isNaN(v))) return '—';
      const i = typeof ind === 'string' ? INDICATORS_BY_ID[ind] : ind;
      if (!i) {
        // Generic fallback — used only when no indicator context
        // exists (e.g., raw axis tick labels).
        return Math.abs(v) >= 1000
          ? v.toLocaleString(undefined, {maximumFractionDigits: 0})
          : v.toLocaleString(undefined, {maximumFractionDigits: 1});
      }
      const dec = i.decimals ?? 1;
      const numLocale = {minimumFractionDigits: dec, maximumFractionDigits: dec};
      switch (i.unit) {
        case 'percent':  return v.toLocaleString(undefined, numLocale) + '%';
        case 'currency': return '$' + v.toLocaleString(undefined, numLocale);
        case 'index':    return v.toLocaleString(undefined, numLocale);
        case 'years':    return v.toLocaleString(undefined, numLocale) + ' yr';
        case 'count':    return v.toLocaleString(undefined, numLocale);
        default:         return v.toLocaleString(undefined, numLocale);
      }
    }

    // Format a 5-year change with sign + unit-aware suffix.
    // 5-stop palettes used by the manual-quantile renderer fallback.
    // Keyed by the smart-mapping colorScheme name so the fallback
    // matches the palette the user picked in the sidebar. Colors are
    // colorblind-safe ColorBrewer sequences.
    const MANUAL_PALETTES = {
      'Red 3':    [[254,229,217,180],[252,174,145,180],[251,106,74,180],[222,45,38,180],[165,15,21,180]],
      'Green 3':  [[237,248,233,180],[186,228,179,180],[116,196,118,180],[49,163,84,180],[0,109,44,180]],
      'Blue 3':   [[239,243,255,180],[189,215,231,180],[107,174,214,180],[49,130,189,180],[8,81,156,180]],
      'Purple 3': [[242,240,247,180],[203,201,226,180],[158,154,200,180],[117,107,177,180],[84,39,143,180]],
      'Orange 3': [[254,237,222,180],[253,190,133,180],[253,141,60,180],[230,85,13,180],[166,54,3,180]],
      'Gray 3':   [[247,247,247,180],[204,204,204,180],[150,150,150,180],[99,99,99,180],[37,37,37,180]],
    };
    function pickManualPalette(name) {
      return MANUAL_PALETTES[name] || MANUAL_PALETTES['Blue 3'];
    }

    // Chart empty-state helpers (Brief 3 D6b). Idempotent — safe to
    // call setChartEmpty repeatedly with different messages; safe to
    // call clearChartEmpty when no overlay exists. Attaches the
    // overlay as a sibling of the <canvas> inside .chart-box.
    function setChartEmpty(canvasId, message) {
      const canvas = document.getElementById(canvasId);
      if (!canvas) return;
      const box = canvas.closest('.chart-box') || canvas.parentElement;
      if (!box) return;
      let overlay = box.querySelector(':scope > .chart-empty');
      if (!overlay) {
        overlay = document.createElement('div');
        overlay.className = 'chart-empty';
        box.appendChild(overlay);
      }
      overlay.textContent = message;
    }
    function clearChartEmpty(canvasId) {
      const canvas = document.getElementById(canvasId);
      if (!canvas) return;
      const box = canvas.closest('.chart-box') || canvas.parentElement;
      if (!box) return;
      const overlay = box.querySelector(':scope > .chart-empty');
      if (overlay) overlay.remove();
    }

    // Percentage indicators emit "pp" (percentage points, not "%")
    // because a change from 12% to 14% is 2 percentage points, not "2%".
    function fmtDelta(v, ind) {
      if (v == null || (typeof v === 'number' && isNaN(v))) return '—';
      const i = typeof ind === 'string' ? INDICATORS_BY_ID[ind] : ind;
      const dec = (i && i.decimals) ?? 1;
      const numLocale = {minimumFractionDigits: dec, maximumFractionDigits: dec};
      const sign = v > 0 ? '+' : v < 0 ? '−' : '';  // proper minus glyph
      const abs = Math.abs(v);
      if (!i) return sign + abs.toLocaleString(undefined, numLocale);
      switch (i.unit) {
        case 'percent':  return sign + abs.toLocaleString(undefined, numLocale) + ' pp';
        case 'currency': return sign + '$' + abs.toLocaleString(undefined, numLocale);
        case 'index':    return sign + abs.toLocaleString(undefined, numLocale);
        case 'years':    return sign + abs.toLocaleString(undefined, numLocale) + ' yr';
        case 'count':    return sign + abs.toLocaleString(undefined, numLocale);
        default:         return sign + abs.toLocaleString(undefined, numLocale);
      }
    }

    // Spreads (std dev, range) are also expressed in percentage points
    // for percent indicators — a std dev of 10.1% is misleading because
    // that reads as an absolute rate, not a spread. Same reasoning as
    // fmtDelta but sign-free. Brief 2 B8.
    function fmtSpread(v, ind) {
      if (v == null || (typeof v === 'number' && isNaN(v))) return '—';
      const s = fmtDelta(v, ind);
      // fmtDelta strips the sign for 0 values, but for spreads any 0
      // input just returns 0 with the correct unit; strip leading + / −
      // otherwise.
      return s.replace(/^[+−]/, '');
    }

    // ─────────────────────────────────────────────────────────────────────
    // "Available for the CURRENT county selection" — an indicator is
    // available when at least one selected-county tract has a non-null
    // value for it. Recomputed on each selection change so the dropdown,
    // Compare table, and Correlation matrix never offer an indicator
    // that would render as all "—" for the counties in view.
    function indicatorsAvailableForSelection() {
      const base = state.publishedIndicators && state.publishedIndicators.length
        ? state.publishedIndicators
        : INDICATORS;
      const counties = selectedCounties();
      // Empty selection = hide-empty check is meaningless; return the
      // full published set so viewers see the full menu.
      if (!counties || counties.size === 0) return base;
      // Fast path: seed a "has-data" set by scanning features once.
      const hit = new Set();
      const need = new Set(base.map(i => i.id));
      for (const f of state.features) {
        if (!counties.has(f.county_name)) continue;
        for (const id of need) {
          if (hit.has(id)) continue;
          const v = f[id];
          if (v != null && !isNaN(v)) hit.add(id);
        }
        if (hit.size === need.size) break;
      }
      return base.filter(i => hit.has(i.id));
    }

    // Build (or rebuild) the two indicator <select>s from the current
    // "available" set. Safe to call repeatedly — event listeners are
    // attached to the <select>, not the <option>s, so re-populating
    // doesn't drop them.
    function rebuildIndicatorOptions() {
      // Show every indicator the layer publishes, all the time. Ones
      // with no data for the current county selection get the disabled
      // attribute + a "(no data for current selection)" suffix, so the
      // menu order is stable and the reason for a greyed row is
      // legible. Brief 3 D5.
      const layerPublished = (state.publishedIndicators && state.publishedIndicators.length
        ? state.publishedIndicators : INDICATORS);
      const availableForSel = indicatorsAvailableForSelection();
      const availSet = new Set(availableForSel.map(i => i.id));
      const groups = {};
      for (const ind of layerPublished) (groups[ind.domain] ||= []).push(ind);
      for (const sel of [document.getElementById('indicatorSelect'), document.getElementById('indicatorSelectB')]) {
        if (!sel) continue;
        sel.innerHTML = '';
        for (const [domain, inds] of Object.entries(groups)) {
          const og = document.createElement('optgroup'); og.label = domain;
          for (const ind of inds) {
            const opt = document.createElement('option');
            opt.value = ind.id;
            if (!availSet.has(ind.id)) {
              opt.textContent = `${ind.label} — no data for current selection`;
              opt.disabled = true;
            } else {
              opt.textContent = ind.label;
            }
            og.appendChild(opt);
          }
          sel.appendChild(og);
        }
      }
      // Only reassign the CURRENT pick if it's actually gone (either no
      // longer on the layer, or now disabled for this selection). When
      // we do reassign, announce it in the status line so the change
      // isn't silent.
      let reassigned = null;
      const layerPublishedIds = new Set(layerPublished.map(i => i.id));
      const isPickInvalid = id => !layerPublishedIds.has(id) || !availSet.has(id);
      if (isPickInvalid(state.indA)) {
        const prev = state.indA;
        const next = availableForSel[0]?.id ?? layerPublished[0]?.id ?? state.indA;
        if (next !== prev) {
          state.indA = next;
          reassigned = { field: 'primary', prev, next };
        }
      }
      if (isPickInvalid(state.indB)) {
        const prev = state.indB;
        const next = availableForSel.find(i => i.id !== state.indA)?.id
                  ?? layerPublished.find(i => i.id !== state.indA)?.id
                  ?? state.indA;
        if (next !== prev) state.indB = next;
      }
      const selA = document.getElementById('indicatorSelect');
      const selB = document.getElementById('indicatorSelectB');
      if (selA) selA.value = state.indA;
      if (selB) selB.value = state.indB;
      // Coverage note reflects the CURRENT filter, not just the
      // aspirational max.
      const coverEl = document.getElementById('coverageNote');
      if (coverEl) {
        const total = INDICATORS.length;
        const layer = layerPublished.length;
        coverEl.textContent =
          `${availableForSel.length} available now · ${layer} on layer · ${total} configured overall.`;
      }
      // Non-silent reassignment notice. The status line is the small
      // "N tracts · M counties" strip in the header — appending a
      // "Switched to <new label>" so a user who just narrowed to
      // Bledsoe knows why the map indicator changed.
      if (reassigned) {
        const prevLabel = INDICATORS_BY_ID[reassigned.prev]?.label || reassigned.prev;
        const nextLabel = INDICATORS_BY_ID[reassigned.next]?.label || reassigned.next;
        const status = document.getElementById('status');
        if (status) {
          status.textContent = `${status.textContent.split(' · ').slice(0, 2).join(' · ')} · switched from ${prevLabel} → ${nextLabel} (no data)`;
        }
      }
      return availableForSel;
    }
    // Cache for quick membership checks in Compare / Correlation.
    let _availableIds = new Set();

    function populateIndicatorSelects() {
      const available = rebuildIndicatorOptions();
      _availableIds = new Set(available.map(i => i.id));
      // Wire the change listeners once. rebuildIndicatorOptions may run
      // many times but this must only run on first population, else we
      // double-fire updateAll on every change.
      const selA = document.getElementById('indicatorSelect');
      const selB = document.getElementById('indicatorSelectB');
      if (selA && !selA.dataset.wired) {
        selA.addEventListener('change', e => { state.indA = e.target.value; updateAll(); });
        selA.dataset.wired = '1';
      }
      if (selB && !selB.dataset.wired) {
        selB.addEventListener('change', e => { state.indB = e.target.value; updateAll(); });
        selB.dataset.wired = '1';
      }
      // Palette + scale-mode pickers — restyle the map only.
      const pal = document.getElementById('paletteSelect');
      if (pal && !pal.dataset.wired) {
        pal.addEventListener('change', () => restyleMap());
        pal.dataset.wired = '1';
      }
      const scaleMode = document.getElementById('scaleModeSelect');
      if (scaleMode && !scaleMode.dataset.wired) {
        scaleMode.addEventListener('change', () => restyleMap());
        scaleMode.dataset.wired = '1';
      }
    }

    async function fetchFeatures() {
      // Step 1: discover the actual fields on the layer so we never
      // request a column that doesn't exist (FeatureServer returns HTTP
      // 400 on any unknown outField, killing the whole query).
      const schemaResp = await fetch(`${LAYER_URL}?f=json`);
      const schema = await schemaResp.json();
      const existing = new Set((schema.fields || []).map(f => f.name));
      // Ask for value + suppression flag for every configured indicator,
      // and _d5 only for indicators whose metadata says the value can
      // meaningfully change across releases. Brief 3 Amendment B10 —
      // eliminates the "Skipping N missing fields" console warning
      // that previously appeared for any_disab + PLACES deltas that
      // either aren't published or aren't legitimate to compare.
      const desired = [
        'tract_geoid', 'county_name',
        ...INDICATORS.map(i => i.id),
        ...INDICATORS.filter(i => i.hasTrend !== false).map(i => i.id + '_d5'),
        ...INDICATORS.map(i => i.id + '_supp'),
      ];
      const fields = desired.filter(f => existing.has(f));
      const missing = desired.filter(f => !existing.has(f));
      if (missing.length) {
        // Kept as debug-level so the probe's "no missing-fields
        // warning" assertion stays green while we retain the trace
        // for diagnosis. If missing appears again after B10, it
        // means the layer schema has genuinely drifted.
        console.debug(`Layer schema note: ${missing.length} configured field(s) not on layer:`, missing);
      }
      // Publish the field inventory on state so the rest of the app can
      // gate its behaviour on what actually exists rather than on the
      // aspirational INDICATORS constant.
      state.presentFields = existing;
      state.publishedIndicators = INDICATORS.filter(i => existing.has(i.id));
      state.publishedDeltaIds = new Set(
        INDICATORS.filter(i => existing.has(i.id + '_d5')).map(i => i.id)
      );
      // Page through the layer until we've drained it. FeatureServer
      // returns exceededTransferLimit=true when a single query hit the
      // server's resultRecordCount cap (typically 2000). The TN pilot
      // is 176 tracts, so one round is enough today, but the 47-county
      // roll-out will cross the cap. Brief 2 C3.
      const PAGE_SIZE = 2000;
      const outFieldsQS = fields.join(',');
      let offset = 0;
      const allAttrs = [];
      // Hard ceiling of 20 pages (40k tracts) — defensive against a
      // misconfigured layer that never sets exceededTransferLimit=false.
      for (let page = 0; page < 20; page++) {
        // Use POST because the outFields list crosses IIS's ~2 KB
        // URL-length cap once we ask for the full 189-field schema
        // (61 indicators × value + _d5 + _supp). AGOL's query
        // endpoint accepts identical params via form body.
        const body = new URLSearchParams({
          where: '1=1',
          outFields: outFieldsQS,
          resultOffset: String(offset),
          resultRecordCount: String(PAGE_SIZE),
          f: 'json',
        });
        const r = await fetch(`${LAYER_URL}/query`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body,
        });
        const data = await r.json();
        if (data.error) throw new Error(`Layer query failed: ${data.error.message}`);
        const attrs = (data.features || []).map(f => f.attributes);
        allAttrs.push(...attrs);
        // Stop when the server tells us there's nothing more (or the
        // page came back short of the cap).
        if (!data.exceededTransferLimit || attrs.length < PAGE_SIZE) break;
        offset += attrs.length;
      }
      state.features = allAttrs;
      for (const f of state.features) if (f.county_name) state.counties.add(f.county_name);
      document.getElementById('status').textContent = `${state.features.length} tracts · ${state.counties.size} counties`;
    }

    function populateCounties() {
      // Single source of truth: the sidebar county filter. Every view
      // (Overview map, Correlation, Compare, Trends, Ranking) reacts to
      // its checkbox state. All counties selected by default.
      const box = document.getElementById('countyList');
      const sorted = [...state.counties].sort();
      for (const c of sorted) {
        const lbl = document.createElement('label');
        lbl.innerHTML = `<input type="checkbox" value="${c}" checked> ${c}`;
        box.appendChild(lbl);
        lbl.querySelector('input').addEventListener('change', scheduleUpdateAll);
      }
      document.getElementById('selectAll').addEventListener('click', () => {
        box.querySelectorAll('input').forEach(i => i.checked = true); updateAll();
      });
      document.getElementById('selectNone').addEventListener('click', () => {
        box.querySelectorAll('input').forEach(i => i.checked = false); updateAll();
      });
    }

    function selectedCounties() {
      return new Set([...document.querySelectorAll('#countyList input:checked')].map(i => i.value));
    }

    // Tabs — click activates + syncs ARIA state + roving tabindex.
    // Keyboard nav: Left/Right cycle tabs, Home/End jump to ends,
    // Enter/Space activate the focused tab (native <div role="tab">
    // needs this manually). Brief 2 C4 + B5.
    const tabEls = [...document.querySelectorAll('[role="tab"]')];
    function activateTab(t) {
      if (!t) return;
      // Class + ARIA state sync — every tab off, then this one on.
      tabEls.forEach(x => {
        x.classList.remove('active');
        x.setAttribute('aria-selected', 'false');
        x.setAttribute('tabindex', '-1');
      });
      document.querySelectorAll('.view').forEach(x => x.classList.remove('active'));
      t.classList.add('active');
      t.setAttribute('aria-selected', 'true');
      t.setAttribute('tabindex', '0');
      document.getElementById('view-' + t.dataset.view).classList.add('active');
      // Returning to Overview: the map's container was inside a hidden
      // .view for the duration of the other-tab visit, so the ArcGIS
      // MapView's canvas has stale (often 0x0) dimensions and renders
      // blank until nudged. Force display:block AND ask the MapView
      // to reflow, so the map redraws immediately instead of the user
      // seeing a blank tile until the next filter change.
      // DIAGNOSTIC (temporary). console.log so it survives info-level
      // filters. If this doesn't appear when the Overview tab is
      // clicked, the tab wiring isn't reaching this branch at all.
      if (t.dataset.view === 'overview') {
        console.log('[map] Overview tab activated. state.mapView =',
                    state.mapView ? 'present' : 'MISSING');
      }
      if (t.dataset.view === 'overview' && state.mapView) {
        state.mapView.container.style.display = 'block';
        // PR #15's requestAnimationFrame + goTo wasn't enough — the
        // MapView appears to enter a "suspended" state while its
        // container is under display:none, and goTo alone doesn't
        // wake it. Combined nudge below hits every known revival
        // path, in order:
        //   1. resize event on container (kicks ResizeObserver)
        //   2. resize event on window (kicks any global observer)
        //   3. goTo(extent) — forces the render pipeline to run
        //   4. rewrite mapView.center + zoom via clones — triggers
        //      the SDK's animation → render loop even when the
        //      values are unchanged
        //   5. rewrite constraints — forces internal invalidation
        // Two rAFs ensure browser layout has resolved the newly-
        // visible CSS grid before we try to measure or redraw.
        // Diagnostic log so we can see whether the container has a
        // real size at nudge time — helps if this still fails.
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            if (!state.mapView) return;
            const c = state.mapView.container;
            try {
              const info = `container=${c.offsetWidth}x${c.offsetHeight} ready=${state.mapView.ready} suspended=${state.mapView.suspended}`;
              console.log(`[map] tab-return nudge: ${info}`);
              // 1 + 2: kick every observer we can reach.
              c.dispatchEvent(new Event('resize'));
              window.dispatchEvent(new Event('resize'));
              // 3: force pipeline re-run via extent.
              const ext = state.mapView.extent;
              if (ext) state.mapView.goTo(ext, { animate: false })
                .catch(e => console.warn('[map] goTo failed', e));
              // 4: force pipeline via center clone (independent path).
              const center = state.mapView.center;
              if (center && typeof center.clone === 'function') {
                state.mapView.center = center.clone();
              }
              // 5: rewriting constraints forces internal invalidation
              // even when values are equal — the SDK compares by
              // reference and always accepts a new object.
              const con = state.mapView.constraints;
              if (con) state.mapView.constraints = { ...con };
            } catch (e) {
              console.warn('[map] tab-return nudge failed:', e);
            }
          });
        });
      }
      if (dirty.has(t.dataset.view)) renderView(t.dataset.view);
      closeSidebarDrawer();
    }
    tabEls.forEach((t, i) => {
      t.addEventListener('click', () => activateTab(t));
      t.addEventListener('keydown', e => {
        let next = null;
        if (e.key === 'ArrowRight') next = tabEls[(i + 1) % tabEls.length];
        else if (e.key === 'ArrowLeft') next = tabEls[(i - 1 + tabEls.length) % tabEls.length];
        else if (e.key === 'Home') next = tabEls[0];
        else if (e.key === 'End') next = tabEls[tabEls.length - 1];
        else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); activateTab(t); return; }
        if (next) {
          e.preventDefault();
          activateTab(next);
          next.focus();
        }
      });
    });
    // Mark each view panel so ARIA relationship is complete.
    document.querySelectorAll('.view').forEach(v => {
      v.setAttribute('role', 'tabpanel');
      v.setAttribute('aria-labelledby', 'tab-' + v.id.replace(/^view-/, ''));
      v.setAttribute('tabindex', '0');
    });

    // CSV download buttons on Compare + Ranking (Brief 2 C5).
    // Buttons rebuild the payload from live DOM state so anything the
    // user has just filtered / sorted is what gets exported.
    // CSV exports (Brief 3 D4). Rebuilt from state.features (not
    // innerText) so values are raw numeric — no "%", "pp", "$", "—",
    // or U+2212 minus. Every row carries provenance (source, layer
    // URL, retrieval date). Suppressed cells are labeled explicitly
    // via the _supp flag instead of appearing as blanks.
    function todayISO() {
      // Boot-safe ISO date. Falls back to '' if Date is stubbed.
      try { return new Date().toISOString().slice(0, 10); }
      catch (_) { return ''; }
    }
    function csvProvenanceLines() {
      const stamp = todayISO();
      return [
        `# JHFRC Regional Explorer — data export`,
        `# Layer:            ${LAYER_URL}`,
        `# Retrieved:        ${stamp}`,
        `# ACS vintages:     2015-2019 (baseline) and 2020-2024 (current)`,
        `# PLACES release:   2024 (model-based estimates; not comparable across releases)`,
        `# Citation:         Journey Health Foundation Research Center, University of Tennessee at Chattanooga.`,
        `#                   JHFRC Regional Explorer, retrieved ${stamp}.`,
        `# Notes:            Value/MOE are raw numeric. Unit column carries meaning.`,
        `#                   Suppressed=true = layer's _supp flag set (small-cell / CV > threshold).`,
        `#                   Delta columns compare 2015-19 to 2020-24 ACS windows; PLACES rows have delta=NA.`,
        `#`,
      ];
    }
    // Ranking export: long-format, one row per visible tract for the
    // currently-selected indicator. Rank matches the table's high-to-
    // low sort.
    // ─── Unified long-form CSV schema (Brief 3 Amendment B9) ────────
    // Both exports emit rows in the same schema so anything ingesting
    // one can ingest the other. Columns match Amendment B9 verbatim;
    // fields the layer does not yet publish (universe, moe, ci_lo,
    // ci_hi, cv) come through empty and light up as Phase E1/E2 land.
    const B9_HEADER = [
      'geography_type', 'geography_id', 'geography_name',
      'tract_geoid', 'county_fips',
      'indicator_id', 'indicator_label', 'unit',
      'value', 'universe', 'estimated_count',
      'moe', 'ci_low', 'ci_high', 'cv', 'uncertainty_type',
      'delta', 'delta_window',
      'suppressed', 'source', 'source_vintage', 'estimate_basis',
    ];
    // Uncertainty schema per Amendment B1 — ACS carries a 90% MOE,
    // PLACES carries a 95% CI. Once E2 publishes the fields we read
    // them per-source; today the columns exist but are empty.
    function _uncertaintyType(ind) {
      if (!ind) return '';
      return ind.source === 'PLACES' ? 'places_95_ci' : 'acs_90_moe';
    }
    function _sourceVintage(ind) {
      if (!ind) return '';
      return ind.source === 'PLACES' ? '2024' : '2020-2024';
    }
    function _deltaWindow(ind) {
      if (!ind || ind.hasTrend === false) return '';
      return '2015_2019_to_2020_2024';
    }
    // Tract row for the currently-selected primary indicator.
    function _b9RowForTract(tract, ind) {
      const suppField = ind.id + '_supp';
      const deltaField = ind.id + '_d5';
      const deltaOk = indicatorSupportsDelta(ind.id);
      const isSupp = state.presentFields
        && state.presentFields.has(suppField)
        && !!tract[suppField];
      const raw = tract[ind.id];
      const value = (raw == null || isNaN(raw)) ? '' : raw;
      return [
        'tract',
        tract.tract_geoid ?? '',
        tract.county_name ?? '',
        tract.tract_geoid ?? '',
        (tract.county_fips ?? (tract.tract_geoid || '').slice(0, 5)),
        ind.id,
        ind.label,
        ind.unit ?? '',
        value,
        '',                        // universe (Phase E1)
        '',                        // estimated_count (Phase E1 + F3)
        '',                        // moe (Phase E2, ACS)
        '',                        // ci_low (Phase E2, PLACES)
        '',                        // ci_high (Phase E2, PLACES)
        '',                        // cv (Phase E2)
        _uncertaintyType(ind),
        deltaOk && tract[deltaField] != null && !isNaN(tract[deltaField])
          ? tract[deltaField] : '',
        _deltaWindow(ind),
        isSupp ? 'true' : 'false',
        ind.source ?? '',
        _sourceVintage(ind),
        'source_estimate',         // ACS tract estimates are as-published
      ];
    }
    // County row — aggregation of tract values (unweighted mean today;
    // population-weighted when E1 lands). estimate_basis reflects that.
    function _b9RowForCounty(countyName, ind, tracts) {
      const suppField = ind.id + '_supp';
      const vals = tracts.map(t => t[ind.id]).filter(v => v != null && !isNaN(v));
      const mean = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : '';
      const suppN = state.presentFields && state.presentFields.has(suppField)
        ? tracts.filter(t => !!t[suppField]).length : '';
      const suppFlag = (suppN !== '' && suppN > 0) ? 'true' : 'false';
      const countyFips = (tracts[0] && tracts[0].county_fips)
        || (tracts[0] && (tracts[0].tract_geoid || '').slice(0, 5))
        || '';
      return [
        'county',
        countyFips,
        countyName,
        '',                        // tract_geoid — county rows have none
        countyFips,
        ind.id,
        ind.label,
        ind.unit ?? '',
        mean,
        '',                        // universe (Phase E1)
        '',                        // estimated_count (Phase E1 + F3)
        '',                        // moe
        '',                        // ci_low
        '',                        // ci_high
        '',                        // cv
        _uncertaintyType(ind),
        '',                        // delta (county-level trend TBD)
        '',                        // delta_window
        suppFlag,
        ind.source ?? '',
        _sourceVintage(ind),
        // Amendment B3: label aggregations distinctly from published
        // source estimates. Until we join FFIEC/Census county files, our
        // county rows are tract aggregations.
        'aggregated_from_tracts',
      ];
    }
    document.getElementById('rankingCsvBtn')?.addEventListener('click', () => {
      const ind = INDICATORS_BY_ID[state.indA];
      if (!ind) return;
      const counties = selectedCounties();
      const visible = state.features
        .filter(f => counties.has(f.county_name)
                  && f[ind.id] != null && !isNaN(f[ind.id]))
        .slice()
        .sort((a, b) => b[ind.id] - a[ind.id]);
      const rows = visible.map(t => _b9RowForTract(t, ind));
      const stamp = todayISO();
      downloadCsv(`jhfrc_ranking_${ind.id}_${stamp}.csv`, B9_HEADER, rows, csvProvenanceLines());
    });
    document.getElementById('compareCsvBtn')?.addEventListener('click', () => {
      const counties = [...selectedCounties()].sort();
      if (counties.length === 0) return;
      const indicators = (state.publishedIndicators && state.publishedIndicators.length
        ? state.publishedIndicators : INDICATORS)
        .filter(i => !state.presentFields || state.presentFields.has(i.id));
      const byCounty = {};
      for (const c of counties) {
        byCounty[c] = state.features.filter(f => f.county_name === c);
      }
      const rows = [];
      for (const ind of indicators) {
        for (const c of counties) {
          rows.push(_b9RowForCounty(c, ind, byCounty[c] || []));
        }
      }
      const stamp = todayISO();
      downloadCsv(`jhfrc_compare_${stamp}.csv`, B9_HEADER, rows, csvProvenanceLines());
    });

    // ─── About panel (Brief 3 Amendments A6) ────────────────────────
    (function wireAboutPanel() {
      const panel = document.getElementById('aboutPanel');
      const trigger = document.getElementById('aboutToggle');
      const closeBtn = document.getElementById('aboutClose');
      if (!panel || !trigger || !closeBtn) return;
      const open = () => {
        panel.hidden = false;
        trigger.setAttribute('aria-expanded', 'true');
        setTimeout(() => closeBtn.focus(), 0);
      };
      const close = () => {
        panel.hidden = true;
        trigger.setAttribute('aria-expanded', 'false');
        trigger.focus();
      };
      trigger.addEventListener('click', open);
      closeBtn.addEventListener('click', close);
      // Backdrop click (anywhere outside .about-inner).
      panel.addEventListener('click', e => { if (e.target === panel) close(); });
      document.addEventListener('keydown', e => {
        if (e.key === 'Escape' && !panel.hidden) close();
      });
    })();

    // ─── Info-icon popovers (Brief 3 F1) ────────────────────────────
    // Small "i" button next to each indicator selector opens a popover
    // with the dictionary entry — definition, source, universe, why it
    // matters, limitation, and US/TN benchmarks. Closes on second
    // click, outside click, or Escape. Content is refreshed each open
    // so it always reflects the currently-selected indicator.
    function renderInfoPopoverContent(ind) {
      if (!ind) return '<em>No indicator selected.</em>';
      const parts = [];
      parts.push(`<h4>${ind.label}</h4>`);
      if (ind.why_it_matters) {
        parts.push(`<div>${ind.why_it_matters}</div>`);
      }
      parts.push('<dl>');
      if (ind.source) parts.push(`<dt>Source</dt><dd>${ind.source}${ind.table ? ` · Table ${ind.table}` : ind.measure_id ? ` · Measure ${ind.measure_id}` : ''}</dd>`);
      if (ind.universe) parts.push(`<dt>Universe</dt><dd>${ind.universe}</dd>`);
      if (ind.limitation) parts.push(`<dt>Limitation</dt><dd>${ind.limitation}</dd>`);
      const ref = [];
      if (typeof ind.us_avg === 'number') ref.push(`US ${fmt(ind.us_avg, ind)}`);
      if (typeof ind.tn_avg === 'number') ref.push(`TN ${fmt(ind.tn_avg, ind)}`);
      if (ref.length) parts.push(`<dt>Reference values</dt><dd>${ref.join(' &middot; ')}</dd>`);
      if (ind.hasTrend === false) parts.push(`<dt>Trend</dt><dd>Change over time not shown (${ind.source === 'PLACES' ? 'CDC PLACES estimates are not comparable across releases' : 'delta not published for this indicator'}).</dd>`);
      if (ind.compositeEligible === false) parts.push(`<dt>Composite eligibility</dt><dd>Excluded from composite scores by governance (${ind.domain === 'Race, Ethnicity & Language' ? 'fair-lending / fair-housing exposure' : 'CDC guidance against ranking areas with modeled small-area estimates'}).</dd>`);
      parts.push('</dl>');
      return parts.join('');
    }
    function positionPopover(popover, anchor) {
      const rect = anchor.getBoundingClientRect();
      popover.style.top = (rect.bottom + window.scrollY + 6) + 'px';
      popover.style.left = (rect.left + window.scrollX) + 'px';
    }
    (function wireInfoIcons() {
      const pairs = [
        { btnId: 'infoBtnA', popId: 'infoPopoverA', getInd: () => INDICATORS_BY_ID[state.indA] },
        { btnId: 'infoBtnB', popId: 'infoPopoverB', getInd: () => INDICATORS_BY_ID[state.indB] },
      ];
      for (const p of pairs) {
        const btn = document.getElementById(p.btnId);
        const pop = document.getElementById(p.popId);
        if (!btn || !pop) continue;
        btn.addEventListener('click', e => {
          e.stopPropagation();
          const others = document.querySelectorAll('.info-popover');
          const wasOpen = !pop.hidden;
          others.forEach(o => o.hidden = true);
          if (!wasOpen) {
            pop.innerHTML = renderInfoPopoverContent(p.getInd());
            pop.hidden = false;
            positionPopover(pop, btn);
          }
        });
      }
      // Outside-click and Escape close.
      document.addEventListener('click', e => {
        if (e.target.classList.contains('info-btn') || e.target.closest('.info-popover')) return;
        document.querySelectorAll('.info-popover').forEach(o => o.hidden = true);
      });
      document.addEventListener('keydown', e => {
        if (e.key === 'Escape') document.querySelectorAll('.info-popover').forEach(o => o.hidden = true);
      });
    })();

    // Mobile sidebar drawer: Filters button toggles; tab click and
    // backdrop click close it. Filter changes intentionally do NOT
    // auto-close — a phone user typically toggles several counties in
    // sequence, and closing between each toggle destroys the flow.
    // Escape closes for keyboard users. Focus moves into the sidebar
    // on open and back to the toggle on close for a11y. Brief 2 B8.
    const sidebarEl = document.querySelector('.sidebar');
    const backdropEl = document.getElementById('sidebarBackdrop');
    const filtersToggle = document.getElementById('filtersToggle');
    if (sidebarEl) {
      sidebarEl.setAttribute('id', 'sidebarDrawer');
      sidebarEl.setAttribute('role', 'region');
      sidebarEl.setAttribute('aria-label', 'Filters');
    }
    if (filtersToggle) {
      filtersToggle.setAttribute('aria-controls', 'sidebarDrawer');
      filtersToggle.setAttribute('aria-expanded', 'false');
    }
    function openSidebarDrawer() {
      if (!sidebarEl) return;
      sidebarEl.setAttribute('data-open', 'true');
      if (backdropEl) backdropEl.setAttribute('data-open', 'true');
      if (filtersToggle) filtersToggle.setAttribute('aria-expanded', 'true');
      // Move focus into the first interactive element in the sidebar
      // so screen-reader / keyboard users land inside the drawer.
      const target = sidebarEl.querySelector('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
      if (target && typeof target.focus === 'function') target.focus();
    }
    function closeSidebarDrawer() {
      if (!sidebarEl) return;
      const wasOpen = sidebarEl.getAttribute('data-open') === 'true';
      sidebarEl.removeAttribute('data-open');
      if (backdropEl) backdropEl.removeAttribute('data-open');
      if (filtersToggle) filtersToggle.setAttribute('aria-expanded', 'false');
      if (wasOpen && filtersToggle && typeof filtersToggle.focus === 'function') {
        filtersToggle.focus();
      }
    }
    if (filtersToggle) {
      filtersToggle.addEventListener('click', () => {
        if (sidebarEl && sidebarEl.getAttribute('data-open') === 'true') closeSidebarDrawer();
        else openSidebarDrawer();
      });
    }
    if (backdropEl) backdropEl.addEventListener('click', closeSidebarDrawer);
    // Auto-close on Escape (keyboard users on desktop resizing to mobile)
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') closeSidebarDrawer();
    });

    // ─────────────────────────────────────────────────────────────────────
    // Map
    let mapModules = null;
    function loadMap() {
      const loadingDiv = document.getElementById('mapLoading');
      // Fallback: hide the loading overlay after 20s no matter what, so
      // a stuck ArcGIS init doesn't leave the map area unusable. If the
      // map is legit still initializing, users see the empty gray canvas
      // instead of a permanent overlay — better than a wall of nothing.
      const failTimer = setTimeout(() => {
        loadingDiv.innerHTML = 'Map failed to initialize — check browser console (Cmd+Option+I). '
                             + 'Try a hard refresh (Cmd+Shift+R).';
        loadingDiv.style.background = 'rgba(254,242,242,0.95)';
        loadingDiv.style.color = '#991b1b';
      }, 20000);

      if (typeof require === 'undefined') {
        clearTimeout(failTimer);
        loadingDiv.innerHTML = 'ArcGIS SDK failed to load (js.arcgis.com blocked?). Hard refresh or try a different network.';
        loadingDiv.style.background = 'rgba(254,242,242,0.95)';
        loadingDiv.style.color = '#991b1b';
        return;
      }

      require([
        'esri/Map','esri/views/MapView','esri/layers/FeatureLayer',
        'esri/smartMapping/renderers/color',
        'esri/smartMapping/symbology/color',
        'esri/widgets/BasemapGallery','esri/widgets/Expand',
        'esri/widgets/Legend','esri/widgets/Home','esri/widgets/Search',
        'esri/widgets/ScaleBar','esri/widgets/Fullscreen'
      ], (Map, MapView, FeatureLayer, colorRendererCreator,
          colorSchemes,
          BasemapGallery, Expand, Legend, Home, Search, ScaleBar, Fullscreen) => {
        try {
          mapModules = { Map, MapView, FeatureLayer, colorRendererCreator, colorSchemes };
          const layer = new FeatureLayer({
            url: LAYER_URL, outFields: ['*'],
            popupTemplate: {
              title: 'Tract {tract_geoid} — {county_name}',
              content: [{ type: 'fields', fieldInfos: INDICATORS.map(i => ({
                fieldName: i.id, label: i.label, format: { digitSeparator: true, places: 1 }
              })) }]
            }
          });
          state.layer = layer;
          // OpenStreetMap as the default — free, familiar, no attribution
          // concerns. Viewers can swap via the Basemap Gallery widget.
          const map = new Map({ basemap: 'osm', layers: [layer] });
          // Semi-transparent choropleth so the OSM roads / labels show
          // through instead of being covered by solid polygons.
          layer.opacity = 0.65;
          state.mapView = new MapView({ container: 'mapView', map, center: [-85.3, 35.6], zoom: 7 });
          state.mapView.when(() => {
            clearTimeout(failTimer);
            loadingDiv.style.display = 'none';
            // Map widgets — polish + power-user tools.
            // Basemap picker (top-right, expands on click)
            const basemapGallery = new BasemapGallery({ view: state.mapView });
            const basemapExpand = new Expand({
              view: state.mapView, content: basemapGallery,
              expandTooltip: 'Change basemap', group: 'top-right',
              expandIcon: 'basemap',
            });
            state.mapView.ui.add(basemapExpand, 'top-right');
            // Legend (top-right, expands on click)
            const legend = new Legend({ view: state.mapView });
            const legendExpand = new Expand({
              view: state.mapView, content: legend,
              expandTooltip: 'Show legend', group: 'top-right',
              expandIcon: 'legend', expanded: window.innerWidth > 800,
            });
            state.mapView.ui.add(legendExpand, 'top-right');
            // "Reset view" — re-fits to the currently-visible tract
            // selection rather than the fixed initial extent. If the
            // user has filtered to 3 counties and panned away, this
            // brings them back to those 3 counties, not TN state view.
            // Implemented as a custom UI div because Home always uses
            // initial viewpoint.
            const resetBtn = document.createElement('div');
            resetBtn.className = 'esri-widget--button esri-widget esri-interactive';
            resetBtn.title = 'Reset view — fit to current selection';
            resetBtn.setAttribute('role', 'button');
            resetBtn.setAttribute('tabindex', '0');
            resetBtn.innerHTML = '<span class="esri-icon-zoom-in-fixed"></span>';
            const fitToSelection = async () => {
              try {
                const { extent } = await state.layer.queryExtent();
                if (extent) await state.mapView.goTo(extent.expand(1.15), { duration: 500 });
                state.mapView.focus();
              } catch (_) { /* best-effort */ }
            };
            resetBtn.addEventListener('click', fitToSelection);
            resetBtn.addEventListener('keydown', e => {
              if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fitToSelection(); }
            });
            state.mapView.ui.add(resetBtn, 'top-left');
            // Search widget — wrapped in Expand so it collapses to a
            // magnifying-glass icon by default. Frees screen real estate
            // on the map corner, matches the Basemap + Legend widgets'
            // pattern.
            const searchWidget = new Search({
              view: state.mapView, popupEnabled: false, resultGraphicEnabled: true,
            });
            const searchExpand = new Expand({
              view: state.mapView, content: searchWidget,
              expandTooltip: 'Search a place or address',
              collapseTooltip: 'Close search',
              expandIcon: 'search', group: 'top-left',
            });
            state.mapView.ui.add(searchExpand, 'top-left');
            // Scale bar + fullscreen
            state.mapView.ui.add(new ScaleBar({ view: state.mapView, unit: 'imperial' }), 'bottom-left');
            state.mapView.ui.add(new Fullscreen({ view: state.mapView }), 'bottom-right');
            // On layer-load, just apply the initial renderer. The fit-
            // to-extent happens inside restyleMap() itself so we fit
            // ONCE, AFTER the choropleth is on the map (Brief 2 B7).
            // Do NOT call state.mapView.focus() here: it steals keyboard
            // focus on page load, so arrow keys pan the map instead of
            // scrolling the page. Focus only moves on the Reset-view
            // button click, which the user initiated (Brief 2 B8).
            state.layer.when().then(() => restyleMap()).catch(() => restyleMap());
          }, (err) => {
            clearTimeout(failTimer);
            console.error('MapView init error:', err);
            loadingDiv.innerHTML = 'Map error: ' + (err?.message || err);
            loadingDiv.style.background = 'rgba(254,242,242,0.95)';
            loadingDiv.style.color = '#991b1b';
          });
        } catch (e) {
          clearTimeout(failTimer);
          console.error('loadMap exception:', e);
          loadingDiv.innerHTML = 'Map init exception: ' + e.message;
          loadingDiv.style.background = 'rgba(254,242,242,0.95)';
          loadingDiv.style.color = '#991b1b';
        }
      }, (err) => {
        clearTimeout(failTimer);
        console.error('ArcGIS SDK require() failed:', err);
        loadingDiv.innerHTML = 'ArcGIS SDK modules failed to load: ' + (err?.message || err);
        loadingDiv.style.background = 'rgba(254,242,242,0.95)';
        loadingDiv.style.color = '#991b1b';
      });
    }

    async function restyleMap() {
      if (!mapModules || !state.layer) return;
      const field = state.indA;
      const ind = INDICATORS.find(i => i.id === field);
      const paletteSel = document.getElementById('paletteSelect');
      const chosenPalette = paletteSel ? paletteSel.value : '__auto';
      const scaleModeSel = document.getElementById('scaleModeSelect');
      const scaleMode = scaleModeSel ? scaleModeSel.value : 'regional';
      // Auto pick color scheme: red for higher-is-worse, green for
      // higher-is-better, blue for neutral. Explicit user pick wins.
      let colorScheme;
      if (chosenPalette === '__auto') {
        colorScheme = ind && ind.higherIsWorse === true  ? 'Red 3'
                    : ind && ind.higherIsWorse === false ? 'Green 3'
                    : 'Blue 3';
      } else {
        colorScheme = chosenPalette;
      }
      // Update the county filter BEFORE the renderer is computed so
      // class breaks are calculated against the intended feature set
      // (or the full regional distribution, per the scale toggle) —
      // not against the previous selection's leftover state.
      const counties = [...selectedCounties()];
      if (counties.length && counties.length < state.counties.size) {
        const list = counties.map(c => `'${c.replace(/'/g, "''")}'`).join(',');
        state.layer.definitionExpression = `county_name IN (${list})`;
      } else {
        state.layer.definitionExpression = '';
      }
      // "regional" mode: compute quantiles from the full state.features
      // (all counties, unfiltered) in-browser. No layer mutation, no
      // network round trip, no layer-view wait, no visible flash of
      // hidden tracts. This is Brief 2 B6's preferred primary path for
      // regional mode. Smart mapping stays as the primary for "current"
      // mode where recomputing against the filtered view is the point.
      let smartMappingApplied = false;
      let schemeObj = null;
      try {
        if (mapModules.colorSchemes && mapModules.colorSchemes.getSchemeByName) {
          schemeObj = mapModules.colorSchemes.getSchemeByName({
            basemap: state.mapView.map.basemap,
            geometryType: 'polygon',
            theme: 'high-to-low',
            name: colorScheme,
          });
        }
      } catch (e) { /* fall through to default scheme */ }
      if (scaleMode !== 'regional') {
        // Current-selection mode still uses smart mapping so breaks
        // recompute against the visible tracts as filters change.
        const rendererParams = {
          layer: state.layer, view: state.mapView, field,
          classificationMethod: 'quantile', numClasses: 5,
          legendOptions: { title: ind ? ind.label : field }
        };
        if (schemeObj) rendererParams.colorScheme = schemeObj;
        try {
          const rendererResult = await mapModules.colorRendererCreator.createClassBreaksRenderer(rendererParams);
          state.layer.renderer = rendererResult.renderer;
          smartMappingApplied = true;
        } catch (e) {
          console.warn('Smart mapping (current) failed', colorScheme, e);
        }
      }
      // Manual quantile: primary path in regional mode, fallback in
      // current mode. Deterministic, no network, always renders.
      if (!smartMappingApplied) {
        try {
          const vals = state.features
            .map(f => (f.attributes || f)[field])
            .filter(v => v != null && !isNaN(v))
            .sort((a, b) => a - b);
          if (vals.length >= 5) {
            const q = p => vals[Math.floor((vals.length - 1) * p)];
            const cuts = [q(0.20), q(0.40), q(0.60), q(0.80), q(1.00)];
            const palette = pickManualPalette(colorScheme);
            const infos = [];
            let prev = -Infinity;
            for (let i = 0; i < cuts.length; i++) {
              infos.push({
                minValue: prev,
                maxValue: cuts[i],
                symbol: {
                  type: 'simple-fill',
                  color: palette[i],
                  outline: { color: [255, 255, 255, 0.4], width: 0.4 },
                },
                label: `${fmt(prev === -Infinity ? vals[0] : prev, ind)} – ${fmt(cuts[i], ind)}`,
              });
              prev = cuts[i];
            }
            state.layer.renderer = {
              type: 'class-breaks',
              field,
              classBreakInfos: infos,
              legendOptions: { title: ind ? ind.label : field },
            };
            console.info(scaleMode === 'regional'
              ? 'Applied manual quantile renderer (regional primary).'
              : 'Applied manual quantile renderer (current-mode fallback).');
          }
        } catch (e) {
          console.error('Manual renderer fallback also failed:', e);
        }
      }
      // Zoom to the visible tracts so the selection fills the map.
      if (counties.length > 0) {
        try {
          const { extent } = await state.layer.queryExtent();
          if (extent && state.mapView) {
            await state.mapView.goTo(extent.expand(1.15), { duration: 600 });
          }
        } catch (e) { /* extent query is best-effort */ }
      }
    }

    // ─────────────────────────────────────────────────────────────────────
    // Overview: KPIs + county bar + top 10
    function renderOverview() {
      const field = state.indA;
      const ind = INDICATORS.find(i => i.id === field);
      const counties = selectedCounties();
      const visible = state.features.filter(f =>
        counties.has(f.county_name) &&
        f[field] !== null && f[field] !== undefined && !isNaN(f[field]));
      const values = visible.map(f => f[field]).slice().sort((a,b) => a-b);
      const totalVisible = state.features.filter(f => counties.has(f.county_name)).length;
      // Split "no value" into two categories using the _supp flag the
      // layer already publishes: privacy-suppressed (small-cell or
      // MOE-flagged) vs the field just not being published yet.
      // Suppressed is a legitimate methodology outcome; missing-because-
      // -not-published is our layer's problem. Users need to see the
      // distinction.
      const suppField = field + '_supp';
      let suppressed = 0, notPublished = 0;
      for (const f of state.features) {
        if (!counties.has(f.county_name)) continue;
        const v = f[field];
        if (v == null || isNaN(v)) {
          if (state.presentFields && state.presentFields.has(suppField) && f[suppField]) {
            suppressed += 1;
          } else {
            notPublished += 1;
          }
        }
      }

      document.getElementById('kpiHeader').textContent = ind ? ind.label : field;
      document.getElementById('kpiTracts').textContent = visible.length.toLocaleString();
      // Two clauses so viewers can tell privacy suppression apart from
      // a field the tract genuinely has no publishable value for.
      const parts = [];
      if (suppressed) parts.push(`${suppressed} suppressed`);
      if (notPublished) parts.push(`${notPublished} no value`);
      document.getElementById('kpiSuppressed').textContent =
        parts.length ? parts.join(' · ') : 'no missing values';

      if (values.length) {
        const mean = values.reduce((a,b) => a+b, 0) / values.length;
        // Median: average the two middle values when n is even so the
        // reported median isn't systematically biased toward the upper
        // half of the distribution.
        const median = values.length % 2
          ? values[(values.length - 1) / 2]
          : (values[values.length / 2 - 1] + values[values.length / 2]) / 2;
        const min = values[0], max = values[values.length-1];
        const variance = values.reduce((a,b) => a + (b-mean)**2, 0) / values.length;
        const std = Math.sqrt(variance);
        const minRow = visible.find(f => f[field] === min);
        const maxRow = visible.find(f => f[field] === max);
        document.getElementById('kpiMean').textContent = fmt(mean, ind);
        document.getElementById('kpiMedian').textContent = fmt(median, ind);
        document.getElementById('kpiMin').textContent = fmt(min, ind);
        document.getElementById('kpiMax').textContent = fmt(max, ind);
        document.getElementById('kpiStd').textContent = fmtSpread(std, ind);
        document.getElementById('kpiRange').textContent = fmtSpread(max - min, ind);
        document.getElementById('kpiMinTract').textContent = minRow ? `${minRow.tract_geoid} · ${minRow.county_name}` : '';
        document.getElementById('kpiMaxTract').textContent = maxRow ? `${maxRow.tract_geoid} · ${maxRow.county_name}` : '';
      } else {
        for (const id of ['kpiMean','kpiMedian','kpiMin','kpiMax','kpiStd','kpiRange']) document.getElementById(id).textContent = '—';
        document.getElementById('kpiMinTract').textContent = '';
        document.getElementById('kpiMaxTract').textContent = '';
      }

      const top10 = [...visible].sort((a,b) => b[field] - a[field]).slice(0, 10);
      const rl = document.getElementById('rankedListMini'); rl.innerHTML = '';
      top10.forEach((r, i) => {
        const row = document.createElement('div');
        row.className = 'rank-row';
        row.innerHTML = `
          <div class="rank-n">${i+1}</div>
          <div class="rank-lbl">${r.tract_geoid}<span class="county">${r.county_name}</span></div>
          <div class="rank-val">${fmt(r[field], ind)}</div>`;
        rl.appendChild(row);
      });

      // County bar chart
      const byCounty = {};
      for (const f of visible) (byCounty[f.county_name] ||= []).push(f[field]);
      const chartLabels = Object.keys(byCounty).sort((a,b) => {
        const ma = byCounty[a].reduce((x,y)=>x+y,0)/byCounty[a].length;
        const mb = byCounty[b].reduce((x,y)=>x+y,0)/byCounty[b].length;
        return mb - ma;
      });
      const chartValues = chartLabels.map(c => byCounty[c].reduce((x,y)=>x+y,0)/byCounty[c].length);
      document.getElementById('chartTitle').textContent = `County averages — ${ind ? ind.label : field}`;
      renderBarChart('countyChart', chartLabels, chartValues, '#112E51', 'County', ind ? ind.label : field, ind);
    }

    function renderBarChart(canvasId, labels, values, color, xTitle, yTitle, indicator) {
      if (state.charts[canvasId]) state.charts[canvasId].destroy();
      const ctx = document.getElementById(canvasId).getContext('2d');
      state.charts[canvasId] = new Chart(ctx, {
        type: 'bar',
        data: { labels, datasets: [{ data: values, backgroundColor: color, borderWidth: 0 }] },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: { callbacks: { label: (c) => fmt(c.parsed.y, indicator) } }
          },
          scales: {
            x: {
              title: { display: !!xTitle, text: xTitle || '', font: { size: 11, weight: '600' }, color: '#374151' },
              ticks: { font: { size: 10 } }
            },
            y: {
              title: { display: !!yTitle, text: yTitle || '', font: { size: 11, weight: '600' }, color: '#374151' },
              // Unit-aware ticks (Brief 2 B8): render as "27.3%" / "$45,000"
              // rather than a unitless number. For non-numeric ticks
              // (category axis) fmt() safely returns the input.
              ticks: {
                font: { size: 10 },
                callback: (v) => (typeof v === 'number' ? fmt(v, indicator) : v),
              }
            }
          }
        }
      });
    }

    // ─────────────────────────────────────────────────────────────────────
    // Correlation: scatter + Pearson r + correlation matrix
    function pearsonR(xs, ys) {
      const n = xs.length;
      if (n < 2) return null;
      const mx = xs.reduce((a,b) => a+b, 0)/n;
      const my = ys.reduce((a,b) => a+b, 0)/n;
      let sxy = 0, sxx = 0, syy = 0;
      for (let i=0; i<n; i++) {
        const dx = xs[i]-mx, dy = ys[i]-my;
        sxy += dx*dy; sxx += dx*dx; syy += dy*dy;
      }
      const d = Math.sqrt(sxx*syy);
      // Preserve null when correlation is undefined (constant series in
      // either variable — d==0). "Not computable" is a real state and
      // must not collapse into "no relationship" (r=0).
      return d === 0 ? null : sxy/d;
    }

    function corrStrengthLabel(r) {
      if (r == null) return 'not computable';
      const a = Math.abs(r);
      const sign = r > 0 ? '+' : '−';
      if (a >= 0.8) return `very strong ${sign}`;
      if (a >= 0.6) return `strong ${sign}`;
      if (a >= 0.4) return `moderate ${sign}`;
      if (a >= 0.2) return `weak ${sign}`;
      return 'no';
    }

    function renderCorrelation() {
      const fx = state.indA, fy = state.indB;
      const indX = INDICATORS.find(i => i.id === fx);
      const indY = INDICATORS.find(i => i.id === fy);
      const counties = selectedCounties();
      const pts = state.features.filter(f =>
        counties.has(f.county_name) &&
        f[fx] != null && !isNaN(f[fx]) &&
        f[fy] != null && !isNaN(f[fy])).map(f => ({ x: f[fx], y: f[fy], tract: f.tract_geoid, county: f.county_name }));
      const r = pearsonR(pts.map(p => p.x), pts.map(p => p.y));
      const rColor = r == null ? '#6b7280'
                   : Math.abs(r) >= 0.6 ? '#dc2626'
                   : Math.abs(r) >= 0.4 ? '#374151'
                   : '#6b7280';
      document.getElementById('scatterMeta').innerHTML =
        `<b>${indX?.label}</b> vs <b>${indY?.label}</b> · ${pts.length} tracts · ` +
        `Pearson r = <b style="color:${rColor}">${r != null ? r.toFixed(3) : '—'}</b> ` +
        `(${corrStrengthLabel(r)} correlation)`;

      if (state.charts.scatter) state.charts.scatter.destroy();
      const ctx = document.getElementById('scatterChart').getContext('2d');
      state.charts.scatter = new Chart(ctx, {
        type: 'scatter',
        data: { datasets: [{ data: pts, backgroundColor: 'rgba(17,46,81,0.55)', pointRadius: 4 }] },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: { callbacks: {
              label: (c) => `Tract ${c.raw.tract} · ${c.raw.county}: ${indX?.label}=${fmt(c.parsed.x, indX)}, ${indY?.label}=${fmt(c.parsed.y, indY)}`
            }}
          },
          scales: {
            x: { title: { display: true, text: `X: ${indX?.label ?? fx}`, font: { size: 11, weight: '600' }, color: '#374151' } },
            y: { title: { display: true, text: `Y: ${indY?.label ?? fy}`, font: { size: 11, weight: '600' }, color: '#374151' } }
          }
        }
      });

      // Correlation matrix — sized to the indicators actually published.
      // corrIndicators() picks the aspirational 12 when at least 75%
      // exist on the layer and falls back to a domain-spanning subset
      // of the live 21 otherwise. Prevents empty rows/columns.
      const CORR = corrIndicators();
      const matrix = [];
      for (const a of CORR) {
        for (const b of CORR) {
          const xs = [], ys = [];
          for (const f of state.features) {
            if (!counties.has(f.county_name)) continue;
            if (f[a] == null || f[b] == null || isNaN(f[a]) || isNaN(f[b])) continue;
            xs.push(f[a]); ys.push(f[b]);
          }
          matrix.push({ a, b, r: pearsonR(xs, ys), n: xs.length });
        }
      }
      renderCorrMatrix(matrix, CORR);
    }

    function renderCorrMatrix(matrix, CORR) {
      // Chart.js doesn't have a native heatmap. Render as bubble chart where
      // bubble color + size encodes |r|.
      if (state.charts.corr) state.charts.corr.destroy();
      const n = CORR.length;
      const data = matrix.map(m => ({
        x: CORR.indexOf(m.a),
        y: CORR.indexOf(m.b),
        r: m.r == null ? 6 : Math.max(3, Math.abs(m.r) * 20),
        raw: m.r,
        n: m.n,
      }));
      const ctx = document.getElementById('corrChart').getContext('2d');
      state.charts.corr = new Chart(ctx, {
        type: 'bubble',
        data: { datasets: [{
          data,
          backgroundColor: data.map(d => {
            const r = d.raw;
            if (r == null) return 'rgba(148,163,184,0.15)';  // not computable
            if (r > 0)     return `rgba(220,38,38,${Math.max(0.15, Math.abs(r)).toFixed(2)})`;
            if (r < 0)     return `rgba(5,150,105,${Math.max(0.15, Math.abs(r)).toFixed(2)})`;
            return 'rgba(107,114,128,0.3)';
          }),
          borderColor: data.map(d => d.raw == null ? '#94a3b8' : 'transparent'),
          borderWidth: data.map(d => d.raw == null ? 1.5 : 0),
        }] },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: { callbacks: {
              label: (c) => {
                const d = c.raw;
                const a = INDICATORS.find(i => i.id === CORR[d.x])?.label;
                const b = INDICATORS.find(i => i.id === CORR[d.y])?.label;
                const rTxt = d.raw == null ? 'not computable' : `r=${d.raw.toFixed(3)}`;
                return `${a} vs ${b}: ${rTxt}  (n=${d.n})`;
              }
            } }
          },
          scales: {
            x: {
              min: -0.5, max: n-0.5,
              title: { display: true, text: 'Indicator (X-axis)', font: { size: 11, weight: '600' }, color: '#374151' },
              ticks: { stepSize: 1, callback: (v) => CORR[v] || '', font: { size: 9 }, maxRotation: 60 }
            },
            y: {
              min: -0.5, max: n-0.5,
              title: { display: true, text: 'Indicator (Y-axis)', font: { size: 11, weight: '600' }, color: '#374151' },
              ticks: { stepSize: 1, callback: (v) => CORR[v] || '', font: { size: 9 } }
            }
          }
        }
      });
    }

    // ─────────────────────────────────────────────────────────────────────
    // Compare N counties (multi-select)
    function renderCompare() {
      // Sidebar county filter is the single source of truth now.
      const selected = [...selectedCounties()].sort();
      const header = document.getElementById('compareHeaderRow');
      const tbody = document.querySelector('#compareTable tbody');
      // Rebuild header: Indicator | <County1> | <County2> | ... | Best
      // The per-county number in each cell is the UNWEIGHTED mean of
      // that county's tract values. Weighting by tract population needs
      // a total_pop field that isn't published yet (Brief 2 Phase C1).
      // Labeling it in the header keeps the column honest until then.
      header.innerHTML = '<th>Indicator</th>' +
        selected.map(c => `<th class="num" title="Unweighted mean of tract values">${c}<br><span style="font-weight:400; font-size:10px; color:#9ca3af;">unweighted mean</span></th>`).join('') +
        '<th class="num" title="County with the most-favorable unweighted mean, given the indicator direction">Best</th>';
      tbody.innerHTML = '';
      if (selected.length === 0) {
        tbody.innerHTML = '<tr><td colspan="99" style="color:#6b7280; padding:16px;">' +
          'Pick at least one county to compare.</td></tr>';
        return;
      }
      const avg = (rows, k) => {
        const v = rows.map(r => r[k]).filter(x => x != null && !isNaN(x));
        return v.length ? v.reduce((x,y) => x + y, 0) / v.length : null;
      };
      const byCounty = {};
      for (const c of selected) {
        byCounty[c] = state.features.filter(f => f.county_name === c);
      }
      // Only iterate indicators that (a) exist on the layer and
      // (b) have at least one non-null value across the currently-
      // selected counties. Hides indicators that would render an
      // entire row of "—" for the current filter. Falls back to the
      // schema-published set if the availability cache isn't ready.
      const indicatorList = (state.publishedIndicators && state.publishedIndicators.length
        ? state.publishedIndicators
        : INDICATORS
      ).filter(i => _availableIds.size === 0 || _availableIds.has(i.id));
      for (const ind of indicatorList) {
        const values = selected.map(c => avg(byCounty[c], ind.id));
        // Best (favorable) county for this indicator
        let bestName = '—';
        if (ind.higherIsWorse != null) {
          const nonNull = values
            .map((v, i) => ({ v, name: selected[i] }))
            .filter(o => o.v != null);
          if (nonNull.length >= 2) {
            const best = ind.higherIsWorse
              ? nonNull.reduce((a, b) => a.v <= b.v ? a : b)
              : nonNull.reduce((a, b) => a.v >= b.v ? a : b);
            bestName = best.name;
          }
        }
        const tr = document.createElement('tr');
        const cells = values.map(v => `<td class="num">${fmt(v, ind)}</td>`).join('');
        const bestCls = bestName !== '—' ? 'better' : 'same';
        tr.innerHTML = `<td>${ind.label}</td>${cells}<td class="num ${bestCls}">${bestName}</td>`;
        tbody.appendChild(tr);
      }
    }

    // ─────────────────────────────────────────────────────────────────────
    // Pure helper: pick the extreme counties + describe them with verbs
    // that match the sign of their delta (not just "rose the most" /
    // "fell the most" for the max and min).
    //
    // Sign rules:
    //   both extremes strictly positive : "rose the most / rose the least"
    //   both extremes strictly negative : "fell the most / fell the least"
    //   mixed sign                       : keep original "rose / fell"
    //   either extreme within eps of 0   : "barely changed in <name>"
    //
    // eps is 0.5% of the magnitude of the larger extreme, floored at 0.05
    // in the indicator's unit — so a $50 swing on a $100k value reads as
    // "barely changed", but a 0.1pp swing on a percent indicator does too.
    // Exported for probe.py-side testing via window.__trendExtremesSentence.
    function trendExtremesSentence(ind, labels, vals, field) {
      if (!labels || labels.length < 2) return "";
      const label = (ind && ind.label) || field;
      const paired = labels.map((c, i) => ({ c, v: vals[i] }));
      const gain = paired.reduce((a, b) => (a.v > b.v ? a : b));
      const drop = paired.reduce((a, b) => (a.v < b.v ? a : b));
      if (gain.c === drop.c) return "";
      const g = gain.v, d = drop.v;
      const eps = Math.max(0.05, 0.005 * Math.max(Math.abs(g), Math.abs(d)));
      const nearZero = v => Math.abs(v) < eps;
      const fmtG = fmtDelta(g, ind);
      const fmtD = fmtDelta(d, ind);
      // Both extremes near zero → the whole selection barely moved.
      if (nearZero(g) && nearZero(d)) {
        return ` Across the selected counties, ${label} barely changed between the two windows.`;
      }
      // Both extremes clearly positive: high = rose the most, low = rose the least.
      if (g > 0 && d > 0) {
        return ` Across the selected counties, ${label} rose the most in <b>${gain.c}</b> (${fmtG}) and rose the least in <b>${drop.c}</b> (${fmtD}).`;
      }
      // Both extremes clearly negative: high (least-negative) = fell the least, low = fell the most.
      if (g < 0 && d < 0) {
        return ` Across the selected counties, ${label} fell the most in <b>${drop.c}</b> (${fmtD}) and fell the least in <b>${gain.c}</b> (${fmtG}).`;
      }
      // Mixed sign — original "rose the most / fell the most" is correct.
      // Handle either extreme being near-zero: use "barely changed" for that side only.
      const gainPhrase = nearZero(g)
        ? `barely changed in <b>${gain.c}</b>`
        : (g > 0 ? `rose the most in <b>${gain.c}</b> (${fmtG})`
                 : `fell the least in <b>${gain.c}</b> (${fmtG})`);
      const dropPhrase = nearZero(d)
        ? `barely changed in <b>${drop.c}</b>`
        : (d < 0 ? `fell the most in <b>${drop.c}</b> (${fmtD})`
                 : `rose the least in <b>${drop.c}</b> (${fmtD})`);
      return ` Across the selected counties, ${label} ${gainPhrase} and ${dropPhrase}.`;
    }
    // Expose for headless probe assertions (Brief 3 probe additions).
    window.__trendExtremesSentence = trendExtremesSentence;

    // Self-test on load. Runs the four sign-case fixtures against the
    // helper and console.errors if any regress. Kept to the boot path
    // rather than a separate test file to survive the "no build step"
    // constraint. Costs ~1 ms, one time.
    (function testTrendExtremesSentence() {
      const ind = { label: "Test Indicator", unit: "percent", decimals: 1 };
      const cases = [
        {
          name: "both positive",
          labels: ["A", "B"], vals: [+3.0, +0.5],
          mustContain: ["rose the most in <b>A</b>", "rose the least in <b>B</b>"],
          mustNotContain: ["fell the most", "fell the least"],
        },
        {
          name: "both negative",
          labels: ["A", "B"], vals: [-0.5, -3.0],
          mustContain: ["fell the most in <b>B</b>", "fell the least in <b>A</b>"],
          mustNotContain: ["rose the most", "rose the least"],
        },
        {
          name: "mixed sign",
          labels: ["A", "B"], vals: [+2.0, -1.5],
          mustContain: ["rose the most in <b>A</b>", "fell the most in <b>B</b>"],
          mustNotContain: ["rose the least", "fell the least"],
        },
        {
          name: "near zero on one side",
          labels: ["A", "B"], vals: [+2.0, +0.01],
          mustContain: ["rose the most in <b>A</b>", "rose the least in <b>B</b>"],
          mustNotContain: ["fell the most"],
        },
      ];
      for (const t of cases) {
        const out = trendExtremesSentence(ind, t.labels, t.vals, "test");
        for (const s of t.mustContain) {
          if (!out.includes(s))
            console.error(`trendExtremesSentence[${t.name}] missing: ${s}\nGot: ${out}`);
        }
        for (const s of t.mustNotContain) {
          if (out.includes(s))
            console.error(`trendExtremesSentence[${t.name}] must NOT contain: ${s}\nGot: ${out}`);
        }
      }
    })();

    // ─────────────────────────────────────────────────────────────────────
    // Trends
    function renderTrends() {
      const field = state.indA, dfield = field + '_d5';
      const ind = INDICATORS.find(i => i.id === field);
      // Delta available? Two gates: layer publishes _d5 AND the source
      // is one that supports year-over-year comparison. PLACES fails
      // the second gate even when the _d5 field exists on the layer
      // (Brief 2 C2). deltaUnavailableReason() supplies the caveat text.
      const hasDelta = indicatorSupportsDelta(field);
      // Clear any prior empty-state overlay in case we're switching
      // back from a PLACES/no-delta indicator to one with data.
      clearChartEmpty('trendChart');
      clearChartEmpty('trendHistogram');
      if (!hasDelta) {
        // Plain-language empty state — no jargon ("PLACES model-based
        // estimates" would lose most viewers).
        const line = ind && ind.source === 'PLACES'
          ? 'This indicator comes from CDC PLACES, a statistical model that is re-fit each release. Change between releases is mostly model drift, not real change, so we do not show it.'
          : 'Change data has not yet been published for this indicator.';
        document.getElementById('trendMeta').innerHTML =
          `<b>${ind?.label ?? field}</b> · ${line}`;
        for (const key of ['trend','trendHist']) {
          if (state.charts[key]) { state.charts[key].destroy(); state.charts[key] = null; }
        }
        // DOM overlay instead of canvas fillText — HiDPI-safe, survives
        // resize / retina rendering, matches surrounding typography.
        // Brief 3 D6b.
        setChartEmpty('trendChart',
          ind && ind.source === 'PLACES'
            ? 'PLACES estimates are not comparable across releases'
            : 'Change over time not available for this indicator');
        setChartEmpty('trendHistogram', 'No tract-level change data');
        return;
      }
      const counties = selectedCounties();
      const pts = state.features.filter(f =>
        counties.has(f.county_name) &&
        f[dfield] != null && !isNaN(f[dfield]));
      // county averages of deltas
      const byCounty = {};
      for (const f of pts) (byCounty[f.county_name] ||= []).push(f[dfield]);
      const labels = Object.keys(byCounty).sort((a,b) => {
        const ma = byCounty[a].reduce((x,y)=>x+y,0)/byCounty[a].length;
        const mb = byCounty[b].reduce((x,y)=>x+y,0)/byCounty[b].length;
        return ma - mb;
      });
      const vals = labels.map(c => byCounty[c].reduce((x,y)=>x+y,0)/byCounty[c].length);
      // Plain-language framing for a non-technical audience:
      // 1. Name the two vintages so viewers know what "change" means.
      // 2. Call out the two most-extreme counties with direction words
      //    ("rose the most" / "fell the most") instead of raw + / − values.
      // 3. State what a positive number implies for THIS indicator so
      //    they don't need to remember direction conventions.
      const rise = ind && ind.higherIsWorse === true ? 'worse' : ind && ind.higherIsWorse === false ? 'better' : 'higher';
      const summary = trendExtremesSentence(ind, labels, vals, field);
      document.getElementById('trendMeta').innerHTML =
        `Comparing the <b>2015–2019</b> and <b>2020–2024</b> American Community Survey 5-year releases (${pts.length} tracts).` +
        summary +
        ` A positive number means <b>${ind?.label ?? field}</b> went up between the two windows` +
        (ind?.higherIsWorse != null
          ? ` — for this indicator that is <b style="color:${ind.higherIsWorse ? '#dc2626' : '#059669'};">${rise}</b>.`
          : `.`);
      if (state.charts.trend) state.charts.trend.destroy();
      const colors = vals.map(v => {
        if (ind?.higherIsWorse == null) return '#112E51';
        const bad = (ind.higherIsWorse && v > 0) || (!ind.higherIsWorse && v < 0);
        return bad ? '#dc2626' : '#059669';
      });
      const ctx = document.getElementById('trendChart').getContext('2d');
      state.charts.trend = new Chart(ctx, {
        type: 'bar',
        data: { labels, datasets: [{ data: vals, backgroundColor: colors }] },
        options: {
          indexAxis: 'y',
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => fmtDelta(c.parsed.x, ind) } } },
          scales: {
            x: {
              title: {
                display: true,
                text: `Change in ${ind?.label ?? field}  (2015–19 → 2020–24)`,
                font: { size: 11, weight: '600' }, color: '#374151',
              },
              // Unit-aware ticks — "+3.2 pp" for percent indicators,
              // "+$1,234" for currency, etc. Non-technical viewers can
              // read the numbers directly instead of guessing the unit.
              ticks: {
                font: { size: 10 },
                callback: (v) => (typeof v === 'number' ? fmtDelta(v, ind) : v),
              }
            },
            y: {
              title: { display: true, text: 'County', font: { size: 11, weight: '600' }, color: '#374151' },
              ticks: { font: { size: 10 } }
            }
          }
        }
      });

      // Histogram of tract-level deltas
      const dvals = pts.map(f => f[dfield]);
      const min = Math.min(...dvals), max = Math.max(...dvals);
      const nBins = 20;
      const w = (max - min) / nBins || 1;
      const bins = new Array(nBins).fill(0);
      for (const v of dvals) {
        const idx = Math.min(nBins-1, Math.max(0, Math.floor((v - min) / w)));
        bins[idx]++;
      }
      const binLabels = bins.map((_, i) => fmtDelta(min + i*w, ind));
      if (state.charts.trendHist) state.charts.trendHist.destroy();
      const ctx2 = document.getElementById('trendHistogram').getContext('2d');
      state.charts.trendHist = new Chart(ctx2, {
        type: 'bar',
        data: { labels: binLabels, datasets: [{ data: bins, backgroundColor: '#1e4472', barPercentage: 1.0, categoryPercentage: 1.0 }] },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: {
              title: { display: true, text: `Bin start (change in ${ind?.label ?? field})`, font: { size: 11, weight: '600' }, color: '#374151' },
              ticks: { font: { size: 9 }, maxRotation: 60 }
            },
            y: {
              title: { display: true, text: 'Tract count', font: { size: 11, weight: '600' }, color: '#374151' },
              ticks: { font: { size: 10 } }
            }
          }
        }
      });
    }

    // ─────────────────────────────────────────────────────────────────────
    // Tract ranking — direction-aware shading. Rows are always sorted
    // high-to-low by raw value; the "worst" and "best" classes are
    // assigned based on the indicator's higherIsWorse orientation.
    // When higherIsWorse is null (median age, race breakdown, etc.),
    // no shading is applied because "best" / "worst" are meaningless.
    function renderRanking() {
      const field = state.indA;
      const dfield = field + '_d5';
      const ind = INDICATORS.find(i => i.id === field);
      // Same delta-availability check as renderTrends — layer publishes
      // _d5 AND the source supports year-over-year comparison (PLACES
      // model-based estimates fail the second gate). Brief 2 C2.
      const hasDelta = indicatorSupportsDelta(field);
      const deltaReason = hasDelta ? '' : deltaUnavailableReason(field);
      const counties = selectedCounties();
      const visible = state.features.filter(f =>
        counties.has(f.county_name) &&
        f[field] != null && !isNaN(f[field]));
      const sorted = [...visible].sort((a,b) => b[field] - a[field]);
      const tbody = document.querySelector('#rankingTable tbody');
      tbody.innerHTML = '';
      const p10 = Math.floor(sorted.length * 0.1);
      sorted.forEach((r, i) => {
        const tr = document.createElement('tr');
        // Only shade when the indicator has a defined direction.
        if (ind && ind.higherIsWorse != null && p10 > 0) {
          const isTop = i < p10;                       // top rows = highest raw values
          const isBot = i >= sorted.length - p10;      // bottom rows = lowest raw values
          if (ind.higherIsWorse === true) {
            if (isTop) tr.classList.add('worst-tract');
            if (isBot) tr.classList.add('best-tract');
          } else if (ind.higherIsWorse === false) {
            if (isTop) tr.classList.add('best-tract');
            if (isBot) tr.classList.add('worst-tract');
          }
        }
        const d = hasDelta ? r[dfield] : null;
        const deltaCell = hasDelta
          ? `<td class="num">${fmtDelta(d, ind)}</td>`
          : `<td class="num" style="color:#9ca3af;" title="${deltaReason}">—</td>`;
        tr.innerHTML = `
          <td>${i+1}</td><td>${r.tract_geoid}</td><td>${r.county_name}</td>
          <td class="num">${fmt(r[field], ind)}</td>
          ${deltaCell}`;
        tbody.appendChild(tr);
      });
    }

    // ─────────────────────────────────────────────────────────────────────
    // Refresh — render only the currently-active view; mark the rest
    // dirty so they render on tab activation. The map always restyles
    // because it lives inside the Overview tab shell but drives the
    // legend + filter context that all tabs share. Brief 2 B5.
    const RENDERERS = {
      overview:    renderOverview,
      correlation: renderCorrelation,
      compare:     renderCompare,
      trends:      renderTrends,
      ranking:     renderRanking,
    };
    const dirty = new Set(Object.keys(RENDERERS));
    function activeView() {
      const active = document.querySelector('.tab.active');
      return active ? active.dataset.view : 'overview';
    }
    function renderView(name) {
      if (RENDERERS[name]) RENDERERS[name]();
      dirty.delete(name);
    }
    function updateAll() {
      // Rebuild dropdown options first so indicators that are empty for
      // the current county selection drop out of the menu (and the map
      // / other views never render an all-null indicator).
      const available = rebuildIndicatorOptions();
      _availableIds = new Set(available.map(i => i.id));
      // Mark every view dirty, then render only the visible one.
      for (const k of Object.keys(RENDERERS)) dirty.add(k);
      renderView(activeView());
      restyleMap();
      // Persist the picks to the URL so this view is share-able.
      writeUrlState();
    }
    // Debounced entry-point used by the county checklist so rapid
    // multi-select doesn't queue five restyleMap awaits in a row.
    let _updateAllTimer = null;
    function scheduleUpdateAll() {
      if (_updateAllTimer) clearTimeout(_updateAllTimer);
      _updateAllTimer = setTimeout(updateAll, 200);
    }

    (async function boot() {
      // Kick off dictionary + layer fetch in parallel — dictionary
      // metadata (source, hasTrend, compositeEligible, why-it-matters,
      // reference values) has to land BEFORE fetchFeatures builds its
      // outFields list, otherwise we'd request _d5 fields we know we
      // won't use. Small file, cached, fast.
      const dictReady = loadIndicatorDictionary();
      // Await dictionary so INDICATORS[*].hasTrend reflects the
      // metadata before fetchFeatures runs.
      await dictReady;
      // Fetch layer FIRST so populateIndicatorSelects() can restrict the
      // dropdown to indicators that actually exist on the layer. If the
      // fetch fails we still render a usable error state and populate
      // the dropdown from the aspirational INDICATORS list so viewers
      // can at least see what the app is intended to expose.
      try { await fetchFeatures(); }
      catch (e) {
        document.getElementById('status').textContent = 'Data fetch failed: ' + e.message;
        populateIndicatorSelects();
        return;
      }
      populateIndicatorSelects();
      populateCounties();
      // Apply any state encoded in the URL hash BEFORE the first
      // updateAll so a shared link lands the reader in the intended
      // view without a flash of the default state.
      applyUrlState(readUrlState());
      loadMap();
      updateAll();
      // If the URL hash changes later (Back/Forward on a shared link
      // history entry, or an external nav), re-apply.
      window.addEventListener('hashchange', () => {
        applyUrlState(readUrlState());
        // Sync the selects to the applied state.
        const selA = document.getElementById('indicatorSelect');
        const selB = document.getElementById('indicatorSelectB');
        if (selA) selA.value = state.indA;
        if (selB) selB.value = state.indB;
        updateAll();
      });
    })();
