import assert from 'node:assert/strict';
import test from 'node:test';

import {
  标准化自适应订阅配置,
  构建自适应运营商配额,
  生成自适应IP,
} from '../_worker.js';

test('自适应订阅默认生成 20 个节点并限制可配置边界', () => {
  const defaults = 标准化自适应订阅配置();
  assert.equal(defaults.启用, true);
  assert.equal(defaults.节点数量, 20);
  assert.deepEqual(defaults.端口, [443, 2053, 2083, 2087, 2096, 8443]);
  assert.equal(defaults.轮换小时, 24);

  assert.equal(标准化自适应订阅配置({ 节点数量: 2 }).节点数量, 8);
  assert.equal(标准化自适应订阅配置({ 节点数量: 200 }).节点数量, 40);
  assert.equal(标准化自适应订阅配置({ 启用: false }).启用, false);
});

test('自适应配额优先当前运营商，同时保留官方与跨网备用节点', () => {
  const mobile = 构建自适应运营商配额('cmcc', 20);
  assert.equal(mobile.reduce((sum, item) => sum + item.数量, 0), 20);
  assert.equal(mobile.find(item => item.运营商 === 'cmcc')?.数量, 8);
  assert.equal(mobile.find(item => item.运营商 === 'cf')?.数量, 5);
  assert.deepEqual(new Set(mobile.map(item => item.运营商)), new Set(['cmcc', 'cf', 'ct', 'cu']));

  const global = 构建自适应运营商配额('cf', 20);
  assert.equal(global.find(item => item.运营商 === 'cf')?.数量, 8);
  assert.equal(global.reduce((sum, item) => sum + item.数量, 0), 20);
});

test('自适应节点合集覆盖四类线路、多个 TLS 端口并支持请求级数量覆盖', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    const value = String(url);
    const cidr = value.includes('/cmcc.txt')
      ? '103.0.0.0/16'
      : value.includes('/cu.txt')
        ? '102.0.0.0/16'
        : value.includes('/ct.txt')
          ? '101.0.0.0/16'
          : '104.16.0.0/13';
    return new Response(cidr, { status: 200 });
  };

  try {
    const request = new Request('https://example.com/sub?cnIspCode=cmcc&nodes=10');
    const [nodes, text] = await 生成自适应IP(request, { 启用: true, 节点数量: 20 });
    const [sameWindowNodes] = await 生成自适应IP(request, { 启用: true, 节点数量: 20 });
    assert.equal(nodes.length, 10);
    assert.deepEqual(sameWindowNodes, nodes);
    assert.equal(new Set(nodes.map(item => item.split('#')[0])).size, 10);
    assert.equal(text.split('\n').length, 10);
    assert.ok(nodes.some(item => item.includes('本网优先-移动')));
    assert.ok(nodes.some(item => item.includes('官方通用')));
    assert.ok(nodes.some(item => item.includes('跨网备用-电信')));
    assert.ok(nodes.some(item => item.includes('跨网备用-联通')));

    const ports = new Set(nodes.map(item => item.match(/:(\d+)#/)?.[1]));
    assert.ok(ports.has('443'));
    assert.ok([...ports].some(port => port !== '443'));
  } finally {
    globalThis.fetch = originalFetch;
  }
});
