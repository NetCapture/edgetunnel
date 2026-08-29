import assert from 'node:assert/strict';
import test from 'node:test';

import {
  标准化监控配置,
  监控字节长度,
  识别监控类型,
  转换监控数值,
  计算60分钟带宽统计,
  在HTML关闭Body前注入,
  构建高精度实时监控注入,
  构建轻量监控汇总模块注入,
  构建管理页面视觉优化注入,
} from '../_worker.js';

test('监控默认开启并限制配置边界', () => {
  const defaults = 标准化监控配置();
  assert.equal(defaults.启用, true);
  assert.equal(defaults.保留天数, 7);
  assert.equal(defaults.刷新秒, 5);
  assert.equal(defaults.GitHub归档.仓库, 'hhhaiai/Picture');
  assert.equal(defaults.GitHub归档.服务名, 'mysimivv');
  assert.equal(defaults.GitHub归档.路径, 'data');
  assert.equal(defaults.GitHub归档.最大本地字节, 2 * 1024 * 1024);
  const bounded = 标准化监控配置({ 启用: false, 保留天数: 100, 刷新秒: 1 });
  assert.equal(bounded.启用, false);
  assert.equal(bounded.保留天数, 30);
  assert.equal(bounded.刷新秒, 3);
});

test('字节统计支持字符串和二进制数据', () => {
  assert.equal(监控字节长度('abc'), 3);
  assert.equal(监控字节长度('你好'), 6);
  assert.equal(监控字节长度(new Uint8Array([1, 2, 3, 4])), 4);
  assert.equal(监控字节长度(new ArrayBuffer(7)), 7);
  assert.equal(监控字节长度(null), 0);
});

test('请求分类覆盖监控、WebSocket、gRPC、订阅和普通页面', () => {
  const request = (path, init = {}) => new Request(`https://example.com${path}`, init);
  assert.equal(识别监控类型(request('/admin/metrics.json')), 'monitor');
  assert.equal(识别监控类型(request('/ws', { headers: { Upgrade: 'websocket' } })), 'ws');
  assert.equal(识别监控类型(request('/rpc', { method: 'POST', headers: { 'content-type': 'application/grpc' } })), 'grpc');
  assert.equal(识别监控类型(request('/sub')), 'sub');
  assert.equal(识别监控类型(request('/admin')), 'admin');
  assert.equal(识别监控类型(request('/')), 'web');
});

test('数值转换对 D1 字符串和非法值安全', () => {
  assert.equal(转换监控数值('42'), 42);
  assert.equal(转换监控数值(undefined), 0);
  assert.equal(转换监控数值('not-a-number'), 0);
});

test('后台增强脚本注入到最后一个 body 闭合标签前', () => {
  const source = '<html><body><script>const example = "</body>";</script><main>ok</main></body></html>';
  const result = 在HTML关闭Body前注入(source, '<script id="monitor"></script>');
  assert.equal(result, '<html><body><script>const example = "</body>";</script><main>ok</main><script id="monitor"></script></body></html>');
});

test('当前后台页面的汇总模块保留独立监控入口', () => {
  const injection = 构建轻量监控汇总模块注入();
  assert.match(injection, /module\.id='lightMonitorModule'/);
  assert.match(injection, /id="lmRequests"/);
  assert.match(injection, /id="lmTotal"/);
  assert.match(injection, /href="\/admin\/monitor"/);
  assert.match(injection, /\/admin\/metrics\.json/);
});

test('管理页面视觉优化保持渐进增强并覆盖桌面与移动端', () => {
  const injection = 构建管理页面视觉优化注入();
  assert.match(injection, /--et-navy:/);
  assert.match(injection, /--et-sky:/);
  assert.match(injection, /--et-orange:/);
  assert.match(injection, /--et-red:/);
  assert.match(injection, /--et-green:/);
  assert.match(injection, /--et-purple:/);
  assert.match(injection, /@media \(max-width:720px\)/);
  assert.match(injection, /min-height:44px/);
  assert.match(injection, /\.social-link\{min-width:44px\}/);
  assert.match(injection, /\.monitor-open-btn\{[^}]*min-height:44px/);
  assert.match(injection, /\.checkbox-group,[^}]*\.checkbox-label\{[^}]*min-height:44px/);
  assert.match(injection, /\.header-title h1\{/);
  assert.match(injection, /prefers-reduced-motion:reduce/);
  assert.match(injection, /low-performance-mode/);
  assert.match(injection, /classList\.add\('edgetunnel-ui-ready'\)/);
  assert.doesNotMatch(injection, /<link\b|<script[^>]+src=/i);
});

test('高精度页面以 5 秒刷新并包含 GitHub 长期归档入口', () => {
  const injection = 构建高精度实时监控注入();
  assert.match(injection, /refreshMs=5000/);
  assert.match(injection, /realtimeSeries/);
  assert.match(injection, /precisionMs/);
  assert.match(injection, /data\/mysimivv/);
  assert.match(injection, /GitHub API/);
});

test('60 分钟带宽统计返回峰值、谷值、活跃谷值和平均值', () => {
  const now = Date.UTC(2026, 7, 30, 1, 0, 0);
  const currentMinute = Math.floor(now / 60000) * 60000;
  const stats = 计算60分钟带宽统计([
    { minute: currentMinute, bytesUp: 2_500_000, bytesDown: 5_000_000 },
    { minute: currentMinute - 60000, bytesUp: 1_250_000, bytesDown: 2_500_000 },
  ], now);
  assert.equal(stats.peakMegabitsPerSecond, 1);
  assert.equal(stats.troughMegabitsPerSecond, 0);
  assert.equal(stats.activeTroughMegabitsPerSecond, 0.5);
  assert.equal(stats.averageMegabitsPerSecond, 0.025);
});
