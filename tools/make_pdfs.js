// Write the printable PDFs from print.html using headless Chromium.
//
//     npm install playwright && npx playwright install chromium   (already installed in the cloud session)
//     node tools/make_pdfs.js
//
// Serves the repo folder on a local port, opens print.html for each workout, and saves
// pdf/<workout id>.pdf plus pdf/yae-all-workouts.pdf. Letter, landscape. Then runs shrink_pdfs.py.
const http = require('http'), fs = require('fs'), path = require('path'), { spawnSync } = require('child_process');
const { chromium } = require('playwright');
const ROOT = path.dirname(__dirname), PDF = path.join(ROOT, 'pdf'), PORT = 8799;
const TYPES = { '.html': 'text/html', '.json': 'application/json', '.webp': 'image/webp', '.css': 'text/css', '.js': 'text/javascript' };

const srv = http.createServer((req, res) => {
  const f = path.join(ROOT, decodeURIComponent(req.url.split('#')[0].split('?')[0]));
  fs.readFile(f, (err, data) => {
    if (err) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { 'Content-Type': TYPES[path.extname(f)] || 'application/octet-stream' }); res.end(data);
  });
}).listen(PORT, '127.0.0.1');

(async () => {
  fs.mkdirSync(PDF, { recursive: true });
  const data = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'yae.json')));
  const ids = data.groups.flatMap(g => g.workouts.map(w => w.id));
  const b = await chromium.launch();
  const page = await b.newPage({ viewport: { width: 1100, height: 850 } });
  for (const id of [...ids, '']) {
    await page.goto(`http://127.0.0.1:${PORT}/print.html#${id}`);
    await page.waitForSelector('.page img');
    await page.evaluate(() => Promise.all([...document.images].map(i => i.complete ? 1 : new Promise(r => { i.onload = i.onerror = r; }))));
    const out = path.join(PDF, (id || 'yae-all-workouts') + '.pdf');
    await page.pdf({ path: out, format: 'Letter', landscape: true, printBackground: true, preferCSSPageSize: true });
    console.log('wrote', path.relative(ROOT, out));
  }
  await b.close(); srv.close();
  // Chromium embeds the photos uncompressed; shrink them to JPEGs.
  spawnSync('python3', [path.join(__dirname, 'shrink_pdfs.py')], { stdio: 'inherit' });
})();
