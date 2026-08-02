import { state } from "../stores/appStore.js";
import { clearStoredSession, createApiClient } from "./http.js";

export const api = createApiClient({
  getToken: () => state.accessToken,
  stripAuthParams: true,
  onUnauthorized: () => {
    state.user = null;
    state.accessToken = "";
    clearStoredSession();
    window.dispatchEvent(new CustomEvent("fitness:unauthorized"));
  },
});

const queryString = (params) => (params instanceof URLSearchParams ? params.toString() : String(params || ""));

export const fitnessApi = {
  getDashboard(params) {
    return api(`/api/dashboard?${queryString(params)}`);
  },
  enrichVenuesByLocation(location, radiusKm = 15) {
    return api(
      `/api/venues/enrich?lat=${encodeURIComponent(location.lat)}&lon=${encodeURIComponent(location.lon)}&radius_km=${radiusKm}`,
    );
  },
  enrichVenues(params) {
    return api(`/api/venues/enrich?${queryString(params)}`);
  },
  getExercises() {
    return api("/api/exercises");
  },
  login(payload) {
    return api("/api/login", { method: "POST", body: JSON.stringify(payload) });
  },
  register(payload) {
    return api("/api/register", { method: "POST", body: JSON.stringify(payload) });
  },
  saveProfile(payload) {
    return api("/api/profile", { method: "POST", body: JSON.stringify(payload) });
  },
  submitSession(payload) {
    return api("/api/session", { method: "POST", body: JSON.stringify(payload) });
  },
  recordPose(payload) {
    return api("/api/pose/record", { method: "POST", body: JSON.stringify(payload) });
  },
  async getAdminData(adminParam) {
    const [
      mapData,
      graphData,
      overviewData,
      usersData,
      venuesData,
      settingsData,
      exercisesData,
      rolesData,
    ] = await Promise.all([
      api(`/api/admin/equipment-map?${adminParam}`),
      api(`/api/admin/knowledge-graph?${adminParam}`),
      api(`/api/admin/overview?${adminParam}`),
      api(`/api/admin/users?${adminParam}`),
      api(`/api/admin/venues?${adminParam}`),
      api(`/api/admin/settings?${adminParam}`),
      api("/api/exercises"),
      api(`/api/admin/roles?${adminParam}`),
    ]);
    return { mapData, graphData, overviewData, usersData, venuesData, settingsData, exercisesData, rolesData };
  },
  saveEquipment(payload) {
    return api("/api/admin/equipment", { method: "POST", body: JSON.stringify(payload) });
  },
  deleteEquipment(id) {
    return api(`/api/admin/equipment/${id}`, { method: "DELETE" });
  },
  saveVenue(payload) {
    return api("/api/admin/venue", { method: "POST", body: JSON.stringify(payload) });
  },
  deleteVenue(id) {
    return api(`/api/admin/venue/${id}`, { method: "DELETE" });
  },
  saveKnowledgeGraph(payload) {
    return api("/api/admin/knowledge-graph", { method: "POST", body: JSON.stringify(payload) });
  },
  deleteKnowledgeEdge(id) {
    return api(`/api/admin/knowledge-graph/${id}`, { method: "DELETE" });
  },
  getAdminUser(params) {
    return api(`/api/admin/user?${queryString(params)}`);
  },
  saveAdminUser(payload) {
    return api("/api/admin/user", { method: "POST", body: JSON.stringify(payload) });
  },
  deleteAdminUser(id) {
    return api(`/api/admin/user/${id}`, { method: "DELETE" });
  },
  recordAdminLog(payload) {
    return api("/api/admin/logs", { method: "POST", body: JSON.stringify(payload) });
  },
  saveAdminExercise(payload) {
    return api("/api/admin/exercise", { method: "POST", body: JSON.stringify(payload) });
  },
  saveAdminRole(payload) {
    return api("/api/admin/role", { method: "POST", body: JSON.stringify(payload) });
  },
  createAnnouncement(payload) {
    return api("/api/admin/announcement", { method: "POST", body: JSON.stringify(payload) });
  },
  saveAdminSettings(payload) {
    return api("/api/admin/settings", { method: "POST", body: JSON.stringify(payload) });
  },
};
