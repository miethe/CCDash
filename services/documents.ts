import { DocumentUpdateRequest, DocumentUpdateResponse } from '../types';
import { apiRequestJson } from './apiClient';

const API_BASE = '/api/documents';

export async function updateDocument(
  docId: string,
  payload: DocumentUpdateRequest,
): Promise<DocumentUpdateResponse> {
  return apiRequestJson<DocumentUpdateResponse>(`${API_BASE}/${encodeURIComponent(docId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}
