const test = require('node:test');
const assert = require('node:assert/strict');
const {
  mergeTrainingPaths,
  normalizeAppKey,
  normalizeFastNavigationThought,
} = require('./capture_server');

test('confirmed partial sessions join by the shared page', () => {
  const paths = [
    [
      { page: '抖音个人主页（我页面）', action: '点购物车图标下的“我的订单”', is_correction: false },
      { page: '抖音订单入口页', action: '点“全部订单”', is_correction: false },
      { page: '抖音的全部订单', action: '让用户选择目标订单', is_correction: false },
      { page: '抖音订单详情', action: '点“申请退款”', is_correction: false },
    ],
    [
      { page: '抖音首页', action: '点右下角的“我”', is_correction: false },
      { page: '抖音个人主页（我页面）', action: '点“我的订单”', is_correction: false },
    ],
  ];

  const merged = mergeTrainingPaths(paths);
  assert.deepEqual(
    merged.map(step => step.page),
    ['抖音首页', '抖音个人主页（我页面）', '抖音订单入口页', '抖音的全部订单', '抖音订单详情'],
  );
  assert.equal(merged.every(step => step.action), true);
});

test('Chinese and package app names normalize to the same key', () => {
  assert.equal(normalizeAppKey('抖音'), 'douyin');
  assert.equal(normalizeAppKey('douyin'), 'douyin');
});

test('newer human correction wins on the same page', () => {
  const merged = mergeTrainingPaths([
    [
      { page: '商城首页', action: '点第二个订单入口', is_correction: false, timestamp: 1 },
    ],
    [
      { page: '商城首页', action: '点全部订单', is_correction: true, timestamp: 2 },
    ],
    [
      { page: '商城首页', action: '点当前显示的第二个订单入口', is_correction: true, timestamp: 3 },
    ],
  ]);

  assert.equal(merged[0].action, '点当前显示的第二个订单入口');
});

test('fast navigation normalizes an unlabeled two-line model response', () => {
  const thought = normalizeFastNavigationThought(
    '抖音商城\n在页面左上方，点击“待发货1”，它是购物车样式的图标',
  );

  assert.equal(
    thought,
    '页面名: 抖音商城\n操作: 在页面左上方，点击“待发货1”，它是购物车样式的图标',
  );
});
