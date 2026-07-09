/**
 * 定时任务状态归一化单测
 */
import { describe, expect, it } from 'vitest';
import {
  isTaskRunning,
  normalizeScheduledTaskRow,
  toBoolFlag,
} from '../scheduledTaskStatus';

describe('scheduledTaskStatus', () => {
  it('toBoolFlag 识别常见真值', () => {
    expect(toBoolFlag(true)).toBe(true);
    expect(toBoolFlag(1)).toBe(true);
    expect(toBoolFlag('1')).toBe(true);
    expect(toBoolFlag('true')).toBe(true);
  });

  it('toBoolFlag 识别常见假值', () => {
    expect(toBoolFlag(false)).toBe(false);
    expect(toBoolFlag(0)).toBe(false);
    expect(toBoolFlag('0')).toBe(false);
    expect(toBoolFlag(null)).toBe(false);
  });

  it('isTaskRunning 依赖归一化后的 is_running', () => {
    expect(isTaskRunning({ is_running: 1 })).toBe(true);
    expect(isTaskRunning({ is_running: 0 })).toBe(false);
  });

  it('normalizeScheduledTaskRow 输出布尔字段', () => {
    const row = normalizeScheduledTaskRow({
      task_name: 'demo',
      is_running: 1,
      is_active: 'true',
    });
    expect(row.is_running).toBe(true);
    expect(row.is_active).toBe(true);
  });
});
