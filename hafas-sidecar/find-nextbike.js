const https = require('https');

function fetch(url) {
  return new Promise((resolve, reject) => {
    https.get(url, res => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve({ status: res.statusCode, body: data }));
      res.on('error', reject);
    }).on('error', reject);
  });
}

(async () => {
  // First try the per-system file we used before
  const direct = await fetch('https://gbfs.nextbike.net/maps/gbfs/v2/nextbike_la/gbfs.json');
  console.log('nextbike_la direct status:', direct.status);
  
  // Now try a few likely candidates for "Lower Austria"
  const candidates = ['nextbike_la', 'nextbike_no', 'nextbike_noe', 'nextbike_at', 'nextbike_lan'];
  for (const sys of candidates) {
    const url = `https://gbfs.nextbike.net/maps/gbfs/v2/${sys}/gbfs.json`;
    const r = await fetch(url);
    console.log(`${sys}: ${r.status}`);
  }
  
  // Also try the v3 path - they may have migrated
  const v3 = await fetch('https://gbfs.nextbike.net/maps/gbfs/v3/nextbike_la/gbfs.json');
  console.log('v3 nextbike_la status:', v3.status);
})();