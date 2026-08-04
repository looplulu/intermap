const test = require('node:test');
const assert = require('node:assert/strict');
const { mergeTrainingPaths, normalizeAppKey } = require('./capture_server');

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
