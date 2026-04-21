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
  
  try {
    const deps = await client.departures(eva, { duration });
    // Slim the response — Python doesn't need all the HAFAS metadata
    const slim = deps.map(d => ({
      tripId:    d.tripId,
      line:      d.line?.name,
      direction: d.direction,
      when:      d.when,            // ISO timestamp with realtime
      plannedWhen: d.plannedWhen,   // ISO timestamp scheduled
      delay:     d.delay,           // seconds, may be null
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