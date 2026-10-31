/* Read-only browser QA for every completed app atlas. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require('playwright');

(async () => {
  const [directory, output] = process.argv.slice(2);
  const state = JSON.parse(fs.readFileSync(path.join(directory, 'batch-index.json')));
  fs.mkdirSync(output, {recursive: true});
  const browser = await chromium.launch({headless: true,
    ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ? {executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE} : {})});
  const results = [];
  const index = await browser.newPage({viewport: {width: 1600, height: 1000}});
  await index.goto(pathToFileURL(path.resolve(directory, 'index.html')).href);
  assert.equal(await index.locator('tbody tr').count(), state.apps.length);
  assert.equal(await index.locator('tbody a').count(), state.apps.filter(x => x.report).length);
  await index.screenshot({path: path.join(output, 'batch-index.png'), fullPage: true});
  await index.setViewportSize({width: 1280, height: 900});
  assert.equal(await index.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  await index.close();
  for (const app of state.apps.filter(x => x.report)) {
    const page = await browser.newPage({viewport: {width: 1600, height: 1000}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(pathToFileURL(path.resolve(directory, app.report)).href);
    assert((await page.title()).startsWith(app.name));
    assert((await page.locator('#diagram .node').count()) > 0, app.key);
    await page.screenshot({path: path.join(output, app.key + '.png')});
    const download = page.waitForEvent('download');
    await page.click('#export');
    assert((await download).suggestedFilename().startsWith(app.key + '-'));
    await page.locator('#evidence summary').first().click();
    assert(await page.locator('#evidence pre').first().isVisible());
    for (const kind of ['template', 'native', 'registry', 'activity']) {
      await page.selectOption('#kind', kind);
      await page.fill('#search', 'intermap_no_such_evidence_000');
      assert.equal(await page.locator('#list .item').count(), 0);
      await page.fill('#search', '');
      if (!(await page.locator('#list .item').count())) continue;
      const bad = await page.locator('#diagram svg').evaluate(svg => [...svg.querySelectorAll('.node')].flatMap(group => {
        const rect = group.querySelector('rect');
        return [...group.querySelectorAll('text')].filter(text => {
          const box = text.getBBox();
          return box.x < 0 || box.y < 0 || box.x + box.width > +rect.getAttribute('width') + 1 || box.y + box.height > +rect.getAttribute('height') + 1;
        }).map(x => x.textContent);
      }));
      assert.deepEqual(bad, [], app.key + ' ' + kind + ' label bounds');
    }
    await page.selectOption('#kind', 'coverage');
    assert((await page.locator('.coverage').innerText()).includes(app.scan_coverage.replace('/', ' / ')));
    await page.setViewportSize({width: 1280, height: 900});
    await page.selectOption('#kind', 'activity');
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    assert.deepEqual(errors, []);
    results.push({app: app.key, browserErrors: errors, result: 'passed'});
    await page.close();
  }
  await browser.close();
  fs.writeFileSync(path.join(output, 'browser-qa.json'), JSON.stringify(results, null, 2));
  console.log(JSON.stringify(results));
})().catch(error => {console.error(error); process.exit(1)});
