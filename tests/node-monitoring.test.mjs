import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import {
  添加节点监控路径,
  解析节点监控标识,
  构建高精度实时监控注入,
  构建节点监控增强注入,
  轻量监控面板HTML,
} from '../_worker.js';

const node = {
  address: '104.16.1.2',
  port: 443,
  group: '官方通用-官方',
};

test('节点监控标识加入路径但不破坏普通、ProxyIP 和链式代理路径', () => {
  const plain = 添加节点监控路径('/', node);
  assert.match(plain, /^\/__etn\/[A-Za-z0-9_-]+\/$/);

  const proxy = 添加节点监控路径('/proxyip=relay.example:443?ed=2560', node);
  assert.match(proxy, /^\/__etn\/[A-Za-z0-9_-]+\/proxyip=relay\.example:443\?ed=2560$/);

  const chained = 添加节点监控路径('/video/opaque-chain-value?ed=2560', node);
  assert.match(chained, /^\/__etn\/[A-Za-z0-9_-]+\/video\/opaque-chain-value\?ed=2560$/);
});

test('节点监控标识可恢复入口 IP、端口与分组并限制非法输入', () => {
  const path = 添加节点监控路径('/service', node);
  const parsed = 解析节点监控标识(new Request(`https://example.com${path}`));
  assert.deepEqual(parsed, {
    id: '104.16.1.2:443',
    ip: '104.16.1.2',
    port: 443,
    group: '官方通用-官方',
  });

  assert.deepEqual(解析节点监控标识(new Request('https://example.com/no-node')), {
    id: '', ip: '', port: 0, group: '',
  });
  assert.deepEqual(解析节点监控标识(new Request('https://example.com/__etn/not-valid!/')), {
    id: '', ip: '', port: 0, group: '',
  });

  const sanitizedPath = 添加节点监控路径('/', { ...node, group: '<img src=x onerror=alert(1)>' });
  const sanitized = 解析节点监控标识(new Request(`https://example.com${sanitizedPath}`));
  assert.doesNotMatch(sanitized.group, /[<>"']/);
});

test('后台监控同时保留用户维度并增加 IP 节点维度', () => {
  const inline = 构建高精度实时监控注入();
  assert.match(inline, /用户监控/);

  const nodeEnhancement = 构建节点监控增强注入();
  assert.match(nodeEnhancement, /data-mode="nodes"/);
  assert.match(nodeEnhancement, /IP节点/);
  assert.match(nodeEnhancement, /id="lmNodeRows"/);
  assert.match(nodeEnhancement, /data\.nodes/);

  const standalone = 轻量监控面板HTML();
  assert.match(standalone, /入口 IP\/节点流量/);
  assert.match(standalone, /id="nodeRows"/);
  assert.match(standalone, /data\.nodes/);
});

test('D1 迁移包含节点维度字段与时间索引', async () => {
  const migration = await readFile(new URL('../monitoring-migration-0003.sql', import.meta.url), 'utf8');
  assert.match(migration, /ADD COLUMN node_ip TEXT/i);
  assert.match(migration, /ADD COLUMN node_port INTEGER/i);
  assert.match(migration, /ADD COLUMN node_group TEXT/i);
  assert.match(migration, /node_ip, node_port, ts/i);
});
