function stripLegacyAuthParams(requestOptions) {
  if (typeof requestOptions.body !== "string") return;
  try {
    const body = JSON.parse(requestOptions.body);
    delete body.user_id;
    delete body.admin_user_id;
    requestOptions.body = JSON.stringify(body);
  } catch (_) {}
}

export function readSessionToken() {
  return sessionStorage.getItem("fitness_access_token") || "";
}

export function clearStoredSession() {
  sessionStorage.removeItem("fitness_access_token");
  sessionStorage.removeItem("fitness_user");
}

export function createApiClient({ getToken = readSessionToken, onUnauthorized = null, stripAuthParams = false } = {}) {
  return async function request(path, options = {}) {
    const url = new URL(path, window.location.origin);
    const requestOptions = { ...options };

    if (stripAuthParams) {
      url.searchParams.delete("user_id");
      url.searchParams.delete("admin_user_id");
      stripLegacyAuthParams(requestOptions);
    }

    const headers = { "Content-Type": "application/json", ...(requestOptions.headers || {}) };
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;

    const response = await fetch(`${url.pathname}${url.search}`, { ...requestOptions, headers });
    const data = await response.json();

    if (response.status === 401 && onUnauthorized) onUnauthorized();
    if (!response.ok) throw new Error(data.message || data.error || data.detail || "请求失败");
    return data.data;
  };
}
