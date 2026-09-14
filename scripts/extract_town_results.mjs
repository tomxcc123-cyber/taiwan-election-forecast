import fs from 'node:fs';

const sourcePath = new URL('../site/base.html', import.meta.url);
const outputPath = new URL('../site/vendor/town-results.json', import.meta.url);
const source = fs.readFileSync(sourcePath, 'utf8');
const match = source.match(/const TOWN = (\{.*?\});\s*const COLORS =/s);

if (!match) throw new Error('Unable to locate the legacy TOWN dataset.');

const towns = JSON.parse(match[1]);
const result = {
  schema_version: 1,
  source: 'CEC election tables already audited by this project',
  note: 'Township/district values are historical election results, not 2026 forecasts.',
  counties: Object.fromEntries(Object.entries(towns).map(([county, elections]) => [county, {
    local_2022: elections.local_exec?.['2022'] || {},
    presidential_2024: elections.presidential?.['2024'] || {},
  }])),
};

fs.writeFileSync(outputPath, `${JSON.stringify(result)}\n`);
console.log(`Wrote ${outputPath.pathname}`);
