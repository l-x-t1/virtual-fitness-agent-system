import { createApiClient } from "./http.js";

const api = createApiClient();

export const aiCoachApi = {
  getStatus() {
    return api("/api/ai/status");
  },
  getSessions() {
    return api("/api/ai/sessions");
  },
  getSession(id) {
    return api(`/api/ai/sessions/${encodeURIComponent(id)}`);
  },
  createSession(payload) {
    return api("/api/ai/sessions", { method: "POST", body: JSON.stringify(payload) });
  },
  deleteSession(id) {
    return api(`/api/ai/sessions/${encodeURIComponent(id)}`, { method: "DELETE" });
  },
  chat(payload) {
    return api("/api/ai/chat", { method: "POST", body: JSON.stringify(payload) });
  },
  createPlan(payload) {
    return api("/api/ai/plans", { method: "POST", body: JSON.stringify(payload) });
  },
  testProvider(payload) {
    return api("/api/ai/providers/test", { method: "POST", body: JSON.stringify(payload) });
  },
};
