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

/** POST /api/v1/ai/conversations -- create a conversation */
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
 * Confirmation for a high-impact action. The frontend sends the confirmation
 * card's approve/reject decision back; the backend executes or cancels the tool
 * call accordingly and returns the updated (or a new) assistant message.
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

/** POST /api/v1/ai/attachments -- upload an attachment (multipart) */
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

/** GET /api/v1/ai/attachments/{id}/file -- fetch an attachment file (image preview) */
export function attachmentFileUrl(attachmentId: string): string {
  return `/api/v1/ai/attachments/${attachmentId}/file`;
}
