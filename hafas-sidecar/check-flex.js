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

const STATION_IDS_TO_CHECK = ['42835', '42845', '3008'];  // Bahnhof, Campus, plus your 3008
const KREMS_BBOX = { minLat: 48.39, maxLat: 48.42, minLon: 15.57, maxLon: 15.62 };

(async () => {
  const base = 'https://gbfs.nextbike.net/maps/gbfs/v2/nextbike_la/en';
  
  console.log('=== Checking specific stations in station_information.json ===\n');
  const info = await fetch(`${base}/station_information.json`);
  const stations = info.data?.stations || [];
  
  for (const id of STATION_IDS_TO_CHECK) {
    const s = stations.find(x => x.station_id === id);
    if (!s) {
      console.log(`Station ${id}: NOT FOUND in station_information\n`);
      continue;
    }
    console.log(`Station ${id}: ${s.name}`);
    console.log(`  is_virtual_station: ${s.is_virtual_station ?? '(not set)'}`);
    console.log(`  capacity:           ${s.capacity ?? '(not set)'}`);
    console.log(`  station_area:       ${s.station_area ? 'present (geofence polygon)' : '(not set)'}`);
    console.log(`  rental_methods:     ${JSON.stringify(s.rental_methods ?? '(not set)')}`);
    console.log('');
  }
  
  console.log('=== Checking the same stations in station_status.json ===\n');
  const status = await fetch(`${base}/station_status.json`);
  const statuses = status.data?.stations || [];
  
  for (const id of STATION_IDS_TO_CHECK) {
    const s = statuses.find(x => x.station_id === id);
    if (!s) {
      console.log(`Station ${id}: NOT FOUND in station_status\n`);
      continue;
    }
    console.log(`Station ${id}:`);
    console.log(`  num_bikes_available:    ${s.num_bikes_available}`);
    console.log(`  num_docks_available:    ${s.num_docks_available}`);
    console.log(`  vehicle_docks_available: ${s.vehicle_docks_available ? JSON.stringify(s.vehicle_docks_available) : '(not set)'}`);
    console.log('');
  }
  
  console.log('=== Checking free_bike_status.json for free-floating bikes near Krems ===\n');
  try {
    const free = await fetch(`${base}/free_bike_status.json`);
    const bikes = free.data?.bikes || [];
    const krems = bikes.filter(b => 
      b.lat >= KREMS_BBOX.minLat && b.lat <= KREMS_BBOX.maxLat &&
      b.lon >= KREMS_BBOX.minLon && b.lon <= KREMS_BBOX.maxLon
    );
    console.log(`Total free-floating bikes in feed: ${bikes.length}`);
    console.log(`Free-floating bikes inside Krems bounding box: ${krems.length}`);
    if (krems.length > 0) {
      console.log('Sample (first 5):');
      krems.slice(0, 5).forEach(b => {
        console.log(`  bike_id=${b.bike_id} at (${b.lat.toFixed(4)}, ${b.lon.toFixed(4)})  reserved=${b.is_reserved} disabled=${b.is_disabled}`);
      });
    }
  } catch (err) {
    console.log(`free_bike_status fetch failed: ${err.message}`);
  }
})();