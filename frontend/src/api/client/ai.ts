import { http } from '@/api/http';
import type {
  AIConfig,
  AIConversation,
  AIMessage,
  SendMessageRequest,
  ConfirmActionRequest,
} from '@/types/ai';

export function fetchAIConversations(signal?: AbortSignal): Promise<AIConversation[]> {
  return http<AIConversation[]>('/api/v1/ai/conversations', { signal });
}

/** POST /api/v1/ai/conversations —— 新建对话 */
export function createAIConversation(signal?: AbortSignal): Promise<AIConversation> {
  return http<AIConversation>('/api/v1/ai/conversations', { method: 'POST', signal });
}

export function fetchAIMessages(
  conversationId: string,
  signal?: AbortSignal,
): Promise<AIMessage[]> {
  return http<AIMessage[]>(`/api/v1/ai/conversations/${conversationId}/messages`, { signal });
}

export function sendAIMessage(
  conversationId: string,
  payload: SendMessageRequest,
  signal?: AbortSignal,
): Promise<AIMessage> {
  return http<AIMessage>(`/api/v1/ai/conversations/${conversationId}/messages`, {
    method: 'POST',
    body: payload,
    signal,
  });
}

export function fetchAIModels(signal?: AbortSignal): Promise<string[]> {
  return http<string[]>('/api/v1/ai/models', { signal });
}

/**
 * 高影响操作确认。前端把确认卡的确认/拒绝回传后端；后端据此执行或取消工具调用，
 * 返回一条更新后的 assistant 消息（或新消息）。
 *
 * TODO(BACKEND): 实现 POST /api/v1/ai/conversations/{id}/confirm，落库并驱动工具执行。
 */
export function confirmAIAction(
  conversationId: string,
  payload: ConfirmActionRequest,
  signal?: AbortSignal,
): Promise<AIMessage> {
  return http<AIMessage>(`/api/v1/ai/conversations/${conversationId}/confirm`, {
    method: 'POST',
    body: payload,
    signal,
  });
}

/**
 * AI 流式回复接口（占位）。当前无后端，先固化调用契约供后续接入。
 *
 * TODO(BACKEND): 后端在 POST /api/v1/ai/conversations/{id}/stream 上以
 *   `text/event-stream` 逐段返回 token。前端实现建议：
 *     const res = await fetch(url, { method:'POST', body, signal });
 *     const reader = res.body!.getReader(); const dec = new TextDecoder();
 *     while (true) { const { done, value } = await reader.read(); if (done) break;
 *       onToken(dec.decode(value, { stream: true })); }
 *   末尾后端应给出完整 AIMessage（含 citations/toolCalls）以对齐最终态。
 */
export async function streamAIMessage(
  conversationId: string,
  payload: SendMessageRequest,
  onToken: (chunk: string) => void,
  signal?: AbortSignal,
): Promise<AIMessage> {
  void conversationId;
  void payload;
  void onToken;
  void signal;
    throw new Error('TODO(BACKEND): AI streaming interface not implemented; wire to backend SSE');
}

export function deleteAIConversation(
  conversationId: string,
  signal?: AbortSignal,
): Promise<{deleted: boolean; conversationId: string}>{
  return http(`/api/v1/ai/conversations/${conversationId}`,{
    method: 'DELETE',
    signal,
  });
}

export function fetchAIConfig(signal?: AbortSignal): Promise<AIConfig> {
  return http<AIConfig>('/api/v1/ai/config', { signal });
}

export function saveAIConfig(config: AIConfig, signal?: AbortSignal): Promise<AIConfig> {
  return http<AIConfig>('/api/v1/ai/config', { method: 'PUT', body: config, signal });
}

/** POST /api/v1/ai/attachments —— 上传附件（multipart） */
export async function uploadAIAttachment(
  conversationId: string,
  file: File,
  signal?: AbortSignal,
): Promise<{ attachmentId: string; filename: string; kind: string }> {
  const form = new FormData();
  form.append('conversationId', conversationId);
  form.append('file', file);
  const response = await fetch('/api/v1/ai/attachments', {
    method: 'POST',
    body: form,
    signal: signal ?? null,
  });
  if (!response.ok) {
    throw new Error(`upload failed: ${response.status}`);
  }
  return response.json();
}

/** GET /api/v1/ai/attachments/{id}/file —— 取附件文件（图片预览用） */
export function attachmentFileUrl(attachmentId: string): string {
  return `/api/v1/ai/attachments/${attachmentId}/file`;
}
