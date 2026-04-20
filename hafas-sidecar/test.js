const createClient = require('oebb-hafas');
const client = createClient('commute-dashboard-test');

const candidates = [
  { id: '1191701', name: 'Hernals (Wien)' },
  { id: '1291701', name: 'Wien Hernals Bahnhst' },
];

(async () => {
  for (const c of candidates) {
    console.log(`\n--- ${c.name} (${c.id}) ---`);
    try {
      const deps = await client.departures(c.id, { duration: 60 });
      console.log(`  ${deps.length} departures in next 60 min`);
      deps.slice(0, 5).forEach(d => {
        const when = d.when ? new Date(d.when).toLocaleTimeString('de-AT', { hour: '2-digit', minute: '2-digit' }) : '?';
        console.log(`    ${when}  ${d.line?.name?.padEnd(12)} → ${d.direction}`);
      });
    } catch (err) {
      console.error(`  Error: ${err.message}`);
    }
  }
})();