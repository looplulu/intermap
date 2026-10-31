/* Offline report smoke and layout checks. Requires Playwright on NODE_PATH. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require('playwright');

(async () => {
  const [report, output] = process.argv.slice(2);
  assert(report && output, 'Provide report HTML and screenshot directory');
  fs.mkdirSync(output, {recursive: true});
  const browser = await chromium.launch({headless: true,
    ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ? {executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE} : {})});
  const page = await browser.newPage({viewport: {width: 1600, height: 1000}});
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(pathToFileURL(path.resolve(report)).href);
  const evidence = await page.locator('#flow-data').evaluate(element => JSON.parse(element.textContent));
  const bindingCount = basename => evidence.graphs.find(g => g.source === 'assets/offline/ecommerce_order_list_component/' + basename + '/main.json').bindings.length;
  assert.equal(await page.locator('#diagram .node').count(), 1 + 3 * bindingCount('to_all_tab'));
  assert.equal(await page.locator('#module-field').isVisible(), false);
  await page.screenshot({path: path.join(output, 'orders.png'), fullPage: true});
  await page.locator('#list .item').nth(1).click();
  assert.equal(await page.locator('#diagram .node').count(), 1 + 3 * bindingCount('product_line'));
  await page.locator('#evidence details').first().locator('summary').click();
  assert(await page.locator('#evidence pre').first().isVisible());
  await page.selectOption('#kind', 'native');
  await page.fill('#search', 'SettingNewVersionActivity');
  await page.locator('#list .item').filter({hasText: '设置页（代码分支）'}).first().click();
  assert((await page.locator('#diagram .node').count()) > 5);
  assert((await page.locator('#evidence').innerText()).includes('//setting/account_safety'));
  await page.screenshot({path: path.join(output, 'settings.png'), fullPage: true});
  const download = page.waitForEvent('download');
  await page.click('#export');
  assert((await download).suggestedFilename().endsWith('.svg'));
  await page.fill('#search', '');
  for (const kind of ['template', 'registry', 'activity']) {
    await page.selectOption('#kind', kind);
    assert((await page.locator('#diagram .node').count()) > 0, kind);
    await page.selectOption('#module', 'settings');
    assert((await page.locator('#list .item').count()) > 0 || kind === 'template', kind);
    await page.selectOption('#module', 'all');
  }
  await page.selectOption('#kind', 'template');
  let templates = 0;
  do {
    const items = page.locator('#list .item');
    const count = await items.count();
    for (let i = 0; i < count; i++) {
      await items.nth(i).click();
      const bounds = await page.locator('#diagram svg').evaluate(svg => {
        const bad = [];
        for (const group of svg.querySelectorAll('.node')) {
          const rect = group.querySelector('rect');
          for (const text of group.querySelectorAll('text')) {
            const box = text.getBBox();
            if (box.x < 0 || box.y < 0 || box.x + box.width > +rect.getAttribute('width') + 1 || box.y + box.height > +rect.getAttribute('height') + 1) bad.push(text.textContent);
          }
        }
        return bad;
      });
      assert.deepEqual(bounds, [], 'Diagram labels must fit their nodes');
      templates++;
    }
    if (await page.locator('#next').isDisabled()) break;
    await page.click('#next');
  } while (true);
  assert.equal(templates, evidence.scan.graphs);
  await page.selectOption('#kind', 'coverage');
  assert((await page.locator('.coverage').innerText()).includes('54 / 54'));
  await page.screenshot({path: path.join(output, 'coverage.png'), fullPage: true});
  await page.setViewportSize({width: 1280, height: 900});
  await page.selectOption('#kind', 'audit');
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  await page.screenshot({path: path.join(output, 'desktop-1280.png'), fullPage: true});
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({templatesChecked: templates, browserErrors: errors, screenshots: output}));
  await browser.close();
})().catch(error => {console.error(error); process.exit(1)});
