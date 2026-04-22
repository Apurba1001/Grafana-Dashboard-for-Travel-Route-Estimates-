const express = require('express');
const createClient = require('oebb-hafas');

const app = express();
const PORT = 3001;
const client = createClient('commute-dashboard');

// Health check — Python uses this to confirm sidecar is up
app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'hafas-sidecar' });
});

// Departures from a station
// GET /departures/1191901?duration=60
app.get('/departures/:eva', async (req, res) => {
  const eva = req.params.eva;
  const duration = parseInt(req.query.duration || '60', 10);
  const railOnly = req.query.rail_only === 'true';
  
  const options = { duration };
  if (railOnly) {
    // oebb-hafas product codes: 'nationalExpress', 'national', 'interregional',
    // 'regional', 'suburban' are the rail classes. Exclude bus, tram, U-Bahn.
    options.products = {
      nationalExpress: true,
      national:        true,
      interregional:   true,
      regional:        true,
      suburban:        true,
      bus:             false,
      tram:            false,
      subway:          false,
      ferry:           false,
      taxi:            false,
    };
  }

  try {
    const deps = await client.departures(eva, options);
    const slim = deps.map(d => ({
      tripId:    d.tripId,
      line:      d.line?.name,
      direction: d.direction,
      when:      d.when,
      plannedWhen: d.plannedWhen,
      delay:     d.delay,
      platform:  d.platform,
      cancelled: d.cancelled || false,
    }));
    res.json({ eva, count: slim.length, departures: slim });
  } catch (err) {
    console.error(`/departures/${eva} failed:`, err.message);
    res.status(502).json({ error: err.message });
  }
});

// Search for stations/stops by name
// GET /locations?query=Undstra%C3%9Fe
app.get('/locations', async (req, res) => {
  const query = req.query.query;
  if (!query) return res.status(400).json({ error: 'query parameter required' });
  try {
    const results = await client.locations(query);
    const slim = results.slice(0, 10).map(loc => ({
      id:        loc.id,
      name:      loc.name,
      latitude:  loc.latitude,
      longitude: loc.longitude,
    }));
    res.json({ query, count: slim.length, results: slim });
  } catch (err) {
    console.error(`/locations query=${query} failed:`, err.message);
    res.status(502).json({ error: err.message });
  }
});

app.listen(PORT, () => {
  console.log(`hafas-sidecar listening on http://localhost:${PORT}`);
  console.log(`  GET /health`);
  console.log(`  GET /departures/:eva?duration=60`);
});