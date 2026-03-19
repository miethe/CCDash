export interface CodebaseFileContentResponse {
  filePath: string;
  absolutePath: string;
  content: string;
  sizeBytes: number;
  truncated: boolean;
  originalSize?: number | null;
}

const API_BASE = '/api/codebase';

export async function getCodebaseFileContent(filePath: string): Promise<CodebaseFileContentResponse> {
  const params = new URLSearchParams({
    path: filePath,
  });
  const res = await fetch(`${API_BASE}/file-content?${params.toString()}`);
  if (!res.ok) {
    throw new Error(`Failed to load file content (${res.status})`);
  }
  return res.json();
}
