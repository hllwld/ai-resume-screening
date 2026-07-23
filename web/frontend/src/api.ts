import type { BatchTask, ParsedResume, SessionStatus } from "./types";

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      const detail = await response.json();
      message =
        typeof detail.detail === "string"
          ? detail.detail
          : detail.detail?.message || message;
    } catch {
      // 保留默认错误。
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

async function requestVoid(url: string, options?: RequestInit): Promise<void> {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message = `请求失败（${response.status}）`;
    try {
      const detail = await response.json();
      message =
        typeof detail.detail === "string"
          ? detail.detail
          : detail.detail?.message || message;
    } catch {
      // 保留默认错误信息。
    }
    throw new Error(message);
  }
}

export function getSession(): Promise<SessionStatus> {
  return request("/api/session");
}

export function login(accessCode: string): Promise<SessionStatus> {
  return request("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ access_code: accessCode }),
  });
}

export function logout(): Promise<void> {
  return requestVoid("/api/auth/logout", { method: "POST" });
}

export function createBatch(
  jobDescription: string,
  customInstructions: string,
  resumes: ParsedResume[],
): Promise<BatchTask> {
  return request("/api/batches", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      job_description: jobDescription,
      custom_instructions: customInstructions,
      candidates: resumes.map((resume) => ({
        client_id: resume.id,
        file_name: resume.fileName,
        resume_text: resume.text,
      })),
    }),
  });
}

export function getBatch(taskId: string): Promise<BatchTask> {
  return request(`/api/batches/${taskId}`);
}

export function cancelBatch(taskId: string): Promise<BatchTask> {
  return request(`/api/batches/${taskId}/cancel`, { method: "POST" });
}

export function deleteBatch(taskId: string): Promise<void> {
  return requestVoid(`/api/batches/${taskId}`, { method: "DELETE" });
}
