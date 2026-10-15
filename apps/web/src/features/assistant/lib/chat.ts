import type { ToolCallTrace } from '../types';

/** 界面里的一条消息。助手的消息额外带上它调了哪些工具。 */
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  toolCalls?: ToolCallTrace[];
  /** 模型到轮次上限还没查完时标记出来，界面上要如实显示 */
  truncated?: boolean;
}

/**
 * 新消息的 id。

 * 用自增序号而不是时间戳：同一次回答里连着生成两条时，时间戳会撞（同一毫秒），
 * React 列表出现重复 key 就会串行——这种 bug 平时看不出来，一出就是错位的消息。
 */
let messageCounter = 0;

export function nextMessageId(seed: number): string {
  messageCounter += 1;
  return `m-${seed}-${messageCounter}`;
}

/** 工具调用在界面上的说法：做了什么、成没成。 */
export function describeToolRun(trace: ToolCallTrace): string {
  // 后端给的 summary 已经带了工具名（「查食材库：返回 3 条」），这里只补「没查到」这个信号，
  // 不重复拼一遍标签
  return trace.ok ? trace.summary : `没查到 · ${trace.summary}`;
}

/** 开场给的示例问题：让人一眼知道这个东西能干什么，而不是对着空框发呆。 */
export const SUGGESTIONS: { title: string; question: string }[] = [
  { title: '今天吃什么', question: '今天午餐供应哪些菜？单份营养是多少？' },
  { title: '油盐糖达标吗', question: '最近两周的油、盐、糖用量达标了吗？' },
  { title: '某道菜怎么做', question: '宫保鸡丁的配方是什么？单份能量多少？' },
  { title: '库里有某样食材吗', question: '食材库里有西兰花吗？它的单价和营养是多少？' },
];
