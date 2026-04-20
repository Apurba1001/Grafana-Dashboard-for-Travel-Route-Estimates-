const https = require('https');

function fetch(url) {
  return new Promise((resolve, reject) => {
    https.get(url, res => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve(JSON.parse(data)));
      res.on('error', reject);
    }).on('error', reject);
  });
}

const STATIONS = {
  '42835': 'Krems / Bahnhof',
  '42845': 'Krems / Campus Donau Uni Krems',
};

(async () => {
  const json = await fetch('https://gbfs.nextbike.net/maps/gbfs/v2/nextbike_la/en/station_status.json');
  const stations = json.data?.stations || [];
  
  for (const [id, label] of Object.entries(STATIONS)) {
    const s = stations.find(x => x.station_id === id);
    if (!s) {
      console.log(`${label} (${id}): NOT FOUND in station_status`);
      continue;
    }
    console.log(`${label} (${id}):`);
    console.log(`  bikes available: ${s.num_bikes_available}`);
    console.log(`  docks available: ${s.num_docks_available}`);
    console.log(`  installed:       ${s.is_installed}`);
    console.log(`  renting:         ${s.is_renting}`);
    console.log(`  returning:       ${s.is_returning}`);
    console.log(`  last reported:   ${s.last_reported ? new Date(s.last_reported * 1000).toLocaleString('de-AT') : '?'}`);
    console.log('');
  }
})();