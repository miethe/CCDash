import { DocumentUpdateRequest, DocumentUpdateResponse } from '../types';

const API_BASE = '/api/documents';

export async function updateDocument(
  docId: string,
  payload: DocumentUpdateRequest,
): Promise<DocumentUpdateResponse> {
  const res = await fetch(`${API_BASE}/${encodeURIComponent(docId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(`Failed to update document (${res.status})`);
  }
  return res.json();
}
