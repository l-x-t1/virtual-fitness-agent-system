const state = {
  user: null,
  dashboard: null,
  reportHistory: [],
  admin: {
    equipment: [],
    venues: [],
    knowledge: { nodes: [], edges: [] },
    overview: null,
    users: [],
    userSegments: [],
    venueRows: [],
    logs: [],
    auditRules: [],
    settings: [],
    exercises: [],
    roles: [],
    map: null,
    markers: [],
  },
  assets: {},
  poseLandmarker: null,
  poseModule: null,
  cameraVideo: null,
  cameraStream: null,
  cameraDeviceId: "",
  cameraRequestId: 0,
  modelReady: false,
  lastVideoTime: -1,
  poseBusy: false,
  latestLandmarks: null,
  lastPoseAt: 0,
  lastLandmarkAt: 0,
  poseScore: 82,
  lastPoseActionAt: 0,
  selectedExercise: "拳击挥击",
  venueSortMode: "match",
  venueFilterMode: "all",
  venueSource: [],
  venueMap: null,
  venueMarkers: [],
  userLocation: null,
  locationLoading: false,
  venueEnrichedKey: "",
  locationWatchId: null,
  venueRefreshTimer: null,
  venueClockTimer: null,
  lastVenueRefreshAt: null,
  poseStats: {
    frames: 0,
    totalScore: 0,
    bestScore: 0,
    reps: 0,
    targetReps: 12,
    lastRepAt: 0,
  },
  run: {
    armSwing: 0,
    legSwing: 0,
    cadence: 0,
    lastStepAt: 0,
    lastStepSide: "",
    lastArmSide: "",
    status: "待开始",
  },
  boxing: {
    leftArm: 0,
    rightArm: 0,
    crouch: 0,
    status: "待开始",
  },
  game: {
    running: false,
    score: 0,
    combo: 0,
    bestCombo: 0,
    timeLeft: 60,
    targets: [],
    particles: [],
    lastSpawn: 0,
    lastFrame: 0,
    loopId: null,
    countdownId: null,
    poseLoopId: null,
    previewLoopId: null,
    poseActive: false,
    poseDriven: false,
    playerLocked: false,
    staticFrameTime: 0,
    finished: false,
    inputFlash: null,
    action: "待开始",
  },
};

const $ = (id) => document.getElementById(id);
const nodesById = (id) => Array.from(document.querySelectorAll(`#${id}`));
const activeNode = (id) => document.querySelector(`.view.active #${id}`) || document.getElementById(id);
const MEDIAPIPE_POSE_BASE = "/static/vendor/mediapipe-pose";
const RUNNING_EXERCISES = new Set(["快走", "节奏冲刺"]);
const BOXING_EXERCISES = new Set(["拳击挥击"]);
const ADMIN_VIEW_IDS = new Set([
  "admin",
  "adminUsers",
  "adminTraining",
  "adminCourses",
  "adminEquipment",
  "adminGames",
  "adminReports",
  "adminManagers",
  "adminSettings",
]);

function isAdminUser() {
  return state.user?.role === "admin";
}

const SHIJIAZHUANG_ENVIRONMENT = {
  location: "石家庄市 · 长安区",
  temperature: 22.9,
  weather: "多云",
  aqi: 62,
  capturedAt: "2026-05-18T09:45",
};

const SHIJIAZHUANG_VENUES = [
  {
    name: "河北体育馆",
    category: "综合馆",
    address: "石家庄市长安区中山东路338号",
    open_hours: "06:00-22:00",
    equipment: "篮球、羽毛球、乒乓球、健身训练区",
    rating: "4.8",
    distance: "1.8km",
    match_score: 96,
    crowd_index: 32,
    air_quality: SHIJIAZHUANG_ENVIRONMENT.aqi,
    reason: "市区综合场馆，适合力量、有氧和球类训练。",
    kind: "indoor",
    icon: "🏟",
    tone: "purple",
  },
  {
    name: "裕彤国际体育中心",
    category: "体育场",
    address: "石家庄市长安区体育北大街与中山东路交口周边",
    open_hours: "06:00-21:30",
    equipment: "田径、足球、看台区、户外体能训练",
    rating: "4.7",
    distance: "2.3km",
    match_score: 92,
    crowd_index: 44,
    air_quality: SHIJIAZHUANG_ENVIRONMENT.aqi,
    reason: "适合快走、慢跑和低到中等强度有氧训练。",
    kind: "outdoor",
    icon: "🏃",
    tone: "teal",
  },
  {
    name: "石家庄市中山体育场",
    category: "体育场",
    address: "石家庄市桥西区自强路117号",
    open_hours: "06:00-21:00",
    equipment: "田径场、足球场、户外活动空间",
    rating: "4.6",
    distance: "3.1km",
    match_score: 89,
    crowd_index: 38,
    air_quality: SHIJIAZHUANG_ENVIRONMENT.aqi,
    reason: "中心城区经典运动场地，适合跑步与基础体能。",
    kind: "outdoor",
    icon: "⚽",
    tone: "blue",
  },
  {
    name: "石家庄全民健身中心",
    category: "健身中心",
    address: "石家庄市裕华区体育南大街与塔南路周边",
    open_hours: "08:00-22:00",
    equipment: "健身器械、操房、体测与康复训练",
    rating: "4.5",
    distance: "4.6km",
    match_score: 88,
    crowd_index: 41,
    air_quality: SHIJIAZHUANG_ENVIRONMENT.aqi,
    reason: "室内训练更稳定，适合空气一般时优先推荐。",
    kind: "indoor",
    icon: "💪",
    tone: "orange",
  },
  {
    name: "中央绿色体育公园",
    category: "户外场地",
    address: "石家庄市桥西区塔南路与解放大街交口周边",
    open_hours: "全天开放",
    equipment: "健身步道、球类场地、休闲活动区",
    rating: "4.6",
    distance: "6.8km",
    match_score: 84,
    crowd_index: 28,
    air_quality: SHIJIAZHUANG_ENVIRONMENT.aqi,
    reason: "户外空间充足，适合快走、拉伸和亲子运动。",
    kind: "outdoor",
    icon: "🌿",
    tone: "green",
  },
  {
    name: "河北奥林匹克体育中心",
    category: "综合场馆",
    address: "石家庄市正定新区起步区",
    open_hours: "09:00-21:00",
    equipment: "体育场、体育馆、游泳跳水馆、网球馆",
    rating: "4.9",
    distance: "14.8km",
    match_score: 82,
    crowd_index: 35,
    air_quality: SHIJIAZHUANG_ENVIRONMENT.aqi,
    reason: "大型综合体育中心，适合专项训练和周末运动。",
    kind: "indoor",
    icon: "🏊",
    tone: "violet",
  },
];

function cleanLabel(value, fallback = "未记录动作") {
  const text = String(value ?? "").trim();
  return (!text || text === "??" || text === "?" || text === "null") ? fallback : text;
}

function formatTime(value) {
  if (!value) return "时间未记录";
  return String(value).replace("T", " ").slice(0, 19);
}

function parseLocalTime(value) {
  if (!value) return null;
  const date = new Date(String(value).replace(" ", "T"));
  return Number.isNaN(date.getTime()) ? null : date;
}

function sameLocalDay(left, right) {
  return left
    && right
    && left.getFullYear() === right.getFullYear()
    && left.getMonth() === right.getMonth()
    && left.getDate() === right.getDate();
}

function weekStart(date) {
  const start = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const day = start.getDay() || 7;
  start.setDate(start.getDate() - day + 1);
  start.setHours(0, 0, 0, 0);
  return start;
}

function buildReportRhythm(report) {
  const sessions = report.sessions || [];
  const now = new Date();
  const currentWeekStart = weekStart(now);
  const computedToday = sessions.filter((item) => sameLocalDay(parseLocalTime(item.created_at), now)).length;
  const computedWeek = sessions.filter((item) => {
    const time = parseLocalTime(item.created_at);
    return time && time >= currentWeekStart && time <= now;
  }).length;
  const rhythm = report.rhythm || {};
  return {
    today: Math.max(Number(rhythm.today_count || 0), computedToday),
    week: Math.max(Number(rhythm.week_count || 0), computedWeek),
    total: Number(rhythm.total_count || report.count || sessions.length || 0),
  };
}

function buildWeeklyRhythm(report) {
  if (Array.isArray(report.weekly_rhythm) && report.weekly_rhythm.length) {
    return report.weekly_rhythm.map((item) => ({
      label: item.label || String(item.date || "").slice(5, 10),
      count: Number(item.count || 0),
      isToday: Boolean(item.is_today),
    }));
  }
  const now = new Date();
  const counts = new Map();
  (report.sessions || []).forEach((item) => {
    const time = parseLocalTime(item.created_at);
    if (!time) return;
    const key = `${String(time.getMonth() + 1).padStart(2, "0")}-${String(time.getDate()).padStart(2, "0")}`;
    counts.set(key, (counts.get(key) || 0) + 1);
  });
  return Array.from({ length: 7 }, (_, index) => {
    const day = new Date(now.getFullYear(), now.getMonth(), now.getDate() - (6 - index));
    const label = `${String(day.getMonth() + 1).padStart(2, "0")}-${String(day.getDate()).padStart(2, "0")}`;
    return { label, count: counts.get(label) || 0, isToday: index === 6 };
  });
}

function reportTypeLabel(value) {
  return value === "monthly" ? "月报" : value === "weekly" ? "周报" : cleanLabel(value, "报告");
}

function showReportModal() {
  const modal = $("reportModal");
  if (!modal) return;
  modal.classList.add("open");
  modal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-lock");
}

function openReportModal(report) {
  $("reportModalTitle").textContent = `${reportTypeLabel(report.report_type)}详情`;
  $("reportModalMeta").textContent = `生成时间：${formatTime(report.generated_at || report.generatedAt)}`;
  $("reportModalBody").innerHTML = `
    <div class="modal-grid">
      <div><strong>训练次数</strong><span>${report.session_count ?? report.count ?? 0}</span></div>
      <div><strong>平均分</strong><span>${report.average_score ?? report.average ?? 0}</span></div>
      <div><strong>薄弱动作</strong><span>${cleanLabel(report.weak_exercise, "暂无")}</span></div>
      <div><strong>建议</strong><span>${report.suggestion || "-"}</span></div>
    </div>
    <p class="modal-summary">${report.summary || ""}</p>
  `;
  showReportModal();
}

function openReportHistoryModal(items = []) {
  $("reportModalTitle").textContent = "历史报告";
  $("reportModalMeta").textContent = "点击任意报告查看详情";
  $("reportModalBody").innerHTML = `
    <div id="reportHistoryList" class="modal-history-list">
      ${items.length ? items.map((item) => `
        <button class="history-item" type="button" data-report='${encodeURIComponent(JSON.stringify(item))}'>
          <div class="history-head">
            <strong>${reportTypeLabel(item.report_type)}</strong>
            <b>${item.average_score} 分</b>
          </div>
          <span class="history-summary">${item.summary}</span>
          <div class="history-meta">
            <em>生成时间</em>
            <small>${formatTime(item.generated_at)}</small>
          </div>
        </button>
      `).join("") : `<div class="empty">暂无历史报告。</div>`}
    </div>
  `;
  $("reportHistoryList")?.querySelectorAll(".history-item").forEach((button) => {
    button.addEventListener("click", () => {
      const raw = button.dataset.report;
      if (raw) openReportModal(JSON.parse(decodeURIComponent(raw)));
    });
  });
  showReportModal();
}

function closeReportModal() {
  const modal = $("reportModal");
  if (!modal) return;
  modal.classList.remove("open");
  modal.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-lock");
}

function getExerciseType(name = state.selectedExercise || "") {
  if (name.includes("\u5feb\u8d70") || name.includes("\u8dd1\u6b65") || name.includes("\u51b2\u523a")) return "running";
  if (name.includes("\u62f3\u51fb") || name.includes("\u6325\u51fb")) return "boxing";
  if (name.includes("\u5f00\u5408") || name.includes("\u6709\u6c27") || name.includes("\u8df3")) return "jumping";
  if (name.includes("\u62c9\u4f38") || name.includes("\u67d4\u97e7")) return "stretch";
  if (name.includes("\u5e73\u677f") || name.includes("\u652f\u6491") || name.includes("\u6838\u5fc3")) return "core";
  if (name.includes("\u6df1\u8e72") || name.includes("\u529b\u91cf")) return "squat";
  if (RUNNING_EXERCISES.has(name)) return "running";
  if (BOXING_EXERCISES.has(name)) return "boxing";
  return "general";
}

function isRunningMode() {
  return getExerciseType() === "running";
}

function isBoxingMode() {
  return getExerciseType() === "boxing";
}

function getExerciseRule(type = getExerciseType()) {
  const rules = {
    running: {
      targetReps: 24,
      startPrompt: "准备快走：摆臂、抬膝、保持节奏",
      cameraPrompt: "摄像头识别中：请正对镜头原地快走或慢跑，系统会根据摆臂、抬膝和步频评分。",
    },
    boxing: {
      targetReps: 12,
      startPrompt: "准备拳击：左拳、右拳、下蹲闪避",
      cameraPrompt: "摄像头识别中：请正对镜头挥左拳、挥右拳或下蹲闪避。",
    },
    jumping: {
      targetReps: 10,
      startPrompt: "准备开合跳：手臂抬起，双脚打开",
      cameraPrompt: "摄像头识别中：手臂抬起并双脚分开时计入开合节奏。",
    },
    stretch: {
      targetReps: 8,
      startPrompt: "准备拉伸：抬高手腕，打开手臂，稳定身体",
      cameraPrompt: "摄像头识别中：系统会根据手腕高度、身体倾斜和手臂展开评分。",
    },
    core: {
      targetReps: 10,
      startPrompt: "准备核心：肩、髋、脚踝保持直线",
      cameraPrompt: "摄像头识别中：系统会根据肩膀、髋部和脚踝的身体线条稳定性评分。",
    },
    squat: {
      targetReps: 8,
      startPrompt: "准备深蹲：髋部下沉，膝盖稳定",
      cameraPrompt: "摄像头识别中：系统会根据膝盖角度和髋部下降评分。",
    },
  };
  return rules[type] || {
    targetReps: 10,
    startPrompt: "准备训练：跟随动作提示完成识别",
    cameraPrompt: "MediaPipe 识别中：请正对镜头完成当前动作。",
  };
}

function loadImage(src) {
  const img = new Image();
  img.src = src;
  return img;
}

state.assets.runningCover = loadImage("/static/covers/cover-running.png");
state.assets.boxingCover = loadImage("/static/covers/cover-boxing.png");
state.assets.jumpingCover = loadImage("/static/covers/cover-jumping.png");
state.assets.stretchCover = loadImage("/static/covers/cover-stretch.png");
state.assets.coreCover = loadImage("/static/covers/cover-core.png");
state.assets.squatCover = loadImage("/static/covers/cover-squat.png");

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "请求失败");
  return data;
}

function setStatus(text, tone = "") {
  const node = $("poseStatus");
  if (!node) return;
  node.textContent = text;
  node.className = `status ${tone}`.trim();
}

function toast(message) {
  return showThemeDialog({
    title: "系统提示",
    message,
    confirmText: "知道了",
    alertOnly: true,
  });
}

function showThemeDialog({ title = "确认操作", message = "", confirmText = "确定", cancelText = "取消", tone = "", alertOnly = false } = {}) {
  return new Promise((resolve) => {
    document.querySelector(".theme-confirm-backdrop")?.remove();
    const backdrop = document.createElement("div");
    backdrop.className = `theme-confirm-backdrop ${tone}`.trim();
    backdrop.innerHTML = `
      <section class="theme-confirm-panel" role="dialog" aria-modal="true" aria-labelledby="themeConfirmTitle">
        <div class="theme-confirm-head">
          <span class="theme-confirm-icon">${tone === "danger" ? "!" : "i"}</span>
          <div>
            <h3 id="themeConfirmTitle">${escapeHtml(title)}</h3>
            <p>${escapeHtml(message)}</p>
          </div>
        </div>
        <div class="theme-confirm-actions">
          ${alertOnly ? "" : `<button type="button" class="theme-confirm-cancel">${escapeHtml(cancelText)}</button>`}
          <button type="button" class="theme-confirm-submit ${tone === "danger" ? "danger-btn" : ""}">${escapeHtml(confirmText)}</button>
        </div>
      </section>
    `;
    const previousOverflow = document.body.style.overflow;
    const cleanup = (result) => {
      backdrop.remove();
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", onKeydown);
      resolve(result);
    };
    const onKeydown = (event) => {
      if (event.key === "Escape") cleanup(false);
    };
    backdrop.addEventListener("click", (event) => {
      if (event.target === backdrop) cleanup(false);
    });
    backdrop.querySelector(".theme-confirm-cancel")?.addEventListener("click", () => cleanup(false));
    backdrop.querySelector(".theme-confirm-submit")?.addEventListener("click", () => cleanup(true));
    document.addEventListener("keydown", onKeydown);
    document.body.style.overflow = "hidden";
    document.body.appendChild(backdrop);
    backdrop.querySelector(".theme-confirm-submit")?.focus();
  });
}

function confirmAction(message, options = {}) {
  return showThemeDialog({
    title: options.title || "确认删除",
    message,
    confirmText: options.confirmText || "确认",
    cancelText: options.cancelText || "取消",
    tone: options.tone || "danger",
  });
}

function setAuthState(isAuthenticated) {
  document.body.classList.toggle("auth-required", !isAuthenticated);
  document.body.classList.toggle("is-authenticated", isAuthenticated);
  document.body.classList.toggle("is-admin", isAuthenticated && isAdminUser());
  document.body.classList.toggle("is-user", isAuthenticated && !isAdminUser());
  document.body.dataset.role = isAuthenticated ? (isAdminUser() ? "admin" : "user") : "guest";
  const railLabel = document.querySelector("#railLoginBtn b");
  const railAvatar = document.querySelector("#railLoginBtn span");
  if (railLabel) railLabel.textContent = isAuthenticated ? "退出登录" : "前往登录";
  if (railAvatar) railAvatar.textContent = isAuthenticated ? "退" : "U";
  document.querySelectorAll(".admin-only").forEach((node) => {
    node.hidden = !isAuthenticated || !isAdminUser();
  });
}

function renderTopUserChrome() {
  const rawName = (state.user?.nickname || "").trim();
  const displayName = isAdminUser()
    ? rawName || "管理员"
    : rawName && !["管理员", "admin"].includes(rawName.toLowerCase())
      ? rawName
      : "李同学";
  if ($("topUserName")) $("topUserName").textContent = displayName;
  if ($("topUserNick")) $("topUserNick").textContent = displayName;
  if ($("welcome")) {
    $("welcome").textContent = state.user
      ? isAdminUser()
        ? `${displayName}，欢迎进入管理工作台`
        : `${displayName}，欢迎回到虚拟训练关卡`
      : "登录后生成个性化训练方案";
  }
}

function showView(viewId) {
  if (!state.user && viewId !== "profile") viewId = "profile";
  if (ADMIN_VIEW_IDS.has(viewId) && !isAdminUser()) viewId = state.user ? "dashboard" : "profile";
  if (isAdminUser() && !ADMIN_VIEW_IDS.has(viewId)) viewId = "admin";
  document.querySelectorAll(".nav").forEach((item) => {
    const active = item.dataset.view === viewId && (!isAdminUser() || !item.dataset.adminTarget || item.dataset.adminTarget === "adminOverviewSection");
    item.classList.toggle("active", active);
  });
  document.querySelectorAll(".view").forEach((item) => {
    item.classList.toggle("active", item.id === viewId);
  });
  if (viewId === "game") {
    const hub = $("trainingHub");
    const workspace = $("trainingWorkspace");
    if (hub && workspace) {
      state.game.running = false;
      workspace.hidden = true;
      workspace.classList.remove("running-layout", "boxing-layout");
      hub.hidden = false;
    }
  }
  if (viewId === "game" && !$("trainingWorkspace")?.hidden) drawGame();
  if (viewId === "venues") {
    startVenueClock();
    startVenueRealtimeUpdates();
    refreshVenueLocationAndData().catch((error) => console.warn("location refresh skipped", error));
    setTimeout(() => renderVenueMap(state.venueSource), 180);
  }
  if (ADMIN_VIEW_IDS.has(viewId)) {
    if (viewId === "adminEquipment" || viewId === "admin") {
      updateBrowserLocation()
        .then(() => loadAdminData())
        .catch((error) => console.warn("admin map location skipped", error));
      setTimeout(() => state.admin.map?.invalidateSize(), 160);
    } else {
      loadAdminData();
    }
  }
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function setUser(user) {
  state.user = user;
  setAuthState(true);
  renderTopUserChrome();
  $("userLevel").textContent = user.level;
  $("userPoints").textContent = user.points;
  $("age").value = user.age;
  $("fitnessLevel").value = user.fitness_level;
  $("injuries").value = user.injuries || "";
  $("preference").value = user.preference || "综合训练";
  $("location").value = user.location || "校园东区";
}

function logout() {
  state.user = null;
  state.dashboard = null;
  state.reportHistory = [];
  setAuthState(false);
  showView("profile");
  setStatus("已退出登录，请重新登录后继续使用。");
}

async function loadDashboard(options = {}) {
  if (!state.user) return;
  if (options.locate) await updateBrowserLocation();
  const params = new URLSearchParams({ user_id: state.user.id });
  if (state.userLocation) {
    params.set("lat", state.userLocation.lat);
    params.set("lon", state.userLocation.lon);
    params.set("location", "浏览器当前位置");
  }
  const dashboard = await api(`/api/dashboard?${params.toString()}`);
  state.dashboard = dashboard;
  renderNotificationSummary(dashboard.notifications || []);
  $("profileSummary").textContent = dashboard.profile_summary;
  renderTodayPlan(dashboard.today_plan);
  renderAgentFlow(dashboard.agent_flow);
  renderExercises(dashboard.recommendations.exercises);
  renderVenues(dashboard.recommendations.venues);
  renderTips(dashboard.tips);
  renderProfileAi(dashboard);
  renderReport(dashboard.report);
  renderBadges(dashboard.badges);
  renderPointLogs(dashboard.point_logs);
  await Promise.all([loadLevels(), loadReportHistory(), loadAgentLogs()]);
}

function updateVenueLocationLabel(text) {
  const node = $("venueCurrentLocation");
  if (node) node.textContent = text;
}

function updateVenueLiveStatus(text) {
  const node = $("venueLiveStatus");
  if (node) node.textContent = text;
}

function updateBrowserLocation() {
  if (!navigator.geolocation || state.locationLoading) return Promise.resolve(state.userLocation);
  state.locationLoading = true;
  updateVenueLocationLabel("正在获取当前位置...");
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude, accuracy } = position.coords;
        state.userLocation = {
          lat: latitude.toFixed(6),
          lon: longitude.toFixed(6),
          accuracy: Math.round(accuracy || 0),
        };
        updateVenueLocationLabel(`当前位置 ${Number(state.userLocation.lat).toFixed(5)}, ${Number(state.userLocation.lon).toFixed(5)}`);
        updateVenueLiveStatus(`定位已更新 · 精度约 ${state.userLocation.accuracy || "--"} 米`);
        state.locationLoading = false;
        resolve(state.userLocation);
      },
      () => {
        updateVenueLocationLabel("石家庄市 · 长安区");
        updateVenueLiveStatus("实时定位未开启，使用默认位置");
        state.locationLoading = false;
        resolve(state.userLocation);
      },
      { enableHighAccuracy: true, timeout: 7000, maximumAge: 60000 },
    );
  });
}

async function refreshVenueLocationAndData() {
  if (!state.user || isAdminUser()) return;
  updateVenueLiveStatus("正在实时更新附近场馆...");
  const before = state.userLocation ? `${state.userLocation.lat},${state.userLocation.lon}` : "";
  const location = await updateBrowserLocation();
  const after = location ? `${location.lat},${location.lon}` : "";
  if (location) await enrichVenueNamesForLocation(location);
  if (after) {
    await loadDashboard();
    state.lastVenueRefreshAt = new Date();
    updateVenueLiveStatus(`实时更新中 · ${state.lastVenueRefreshAt.toLocaleTimeString("zh-CN", { hour12: false })}`);
  } else {
    setTimeout(() => state.venueMap?.invalidateSize(), 120);
  }
}

async function enrichVenueNamesForLocation(location) {
  if (!isAdminUser()) return;
  const key = `${Number(location.lat).toFixed(2)},${Number(location.lon).toFixed(2)}`;
  if (state.venueEnrichedKey === key) return;
  state.venueEnrichedKey = key;
  try {
    await api(`/api/venues/enrich?lat=${encodeURIComponent(location.lat)}&lon=${encodeURIComponent(location.lon)}&radius_km=15`);
  } catch (error) {
    console.warn("venue name enrichment skipped", error);
  }
}

function startVenueRealtimeUpdates() {
  if (!navigator.geolocation || !state.user || isAdminUser()) return;
  if (!state.locationWatchId) {
    state.locationWatchId = navigator.geolocation.watchPosition(
      async (position) => {
        const { latitude, longitude, accuracy } = position.coords;
        const next = {
          lat: latitude.toFixed(6),
          lon: longitude.toFixed(6),
          accuracy: Math.round(accuracy || 0),
        };
        const movedMeters = state.userLocation
          ? distanceMeters(state.userLocation.lat, state.userLocation.lon, next.lat, next.lon)
          : Infinity;
        state.userLocation = next;
        updateVenueLocationLabel(`当前位置 ${Number(next.lat).toFixed(5)}, ${Number(next.lon).toFixed(5)}`);
        if (movedMeters >= 30 || !state.lastVenueRefreshAt) {
          await refreshVenueLocationAndData();
        } else {
          updateVenueLiveStatus(`实时定位中 · 精度约 ${next.accuracy || "--"} 米`);
          renderVenueMap(state.venueSource);
        }
      },
      () => updateVenueLiveStatus("实时定位未开启，使用最近一次位置"),
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 15000 },
    );
  }
  if (!state.venueRefreshTimer) {
    state.venueRefreshTimer = setInterval(() => {
      if (document.querySelector("#venues.view.active")) {
        refreshVenueLocationAndData().catch((error) => console.warn("realtime venue refresh skipped", error));
      }
    }, 60000);
  }
}

function distanceMeters(lat1, lon1, lat2, lon2) {
  const radius = 6371000;
  const phi1 = Number(lat1) * Math.PI / 180;
  const phi2 = Number(lat2) * Math.PI / 180;
  const deltaPhi = (Number(lat2) - Number(lat1)) * Math.PI / 180;
  const deltaLambda = (Number(lon2) - Number(lon1)) * Math.PI / 180;
  const a = Math.sin(deltaPhi / 2) ** 2 + Math.cos(phi1) * Math.cos(phi2) * Math.sin(deltaLambda / 2) ** 2;
  return radius * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function renderTodayPlan(plan) {
  const node = $("todayPlan");
  if (!node || !plan) return;
  node.classList.remove("empty");
  node.innerHTML = `
    <div class="plan-head">
      <strong>${plan.title}</strong>
      <span>${plan.duration_minutes} 分钟 / ${plan.intensity}</span>
    </div>
    <div class="plan-steps">
      ${plan.steps.map((step, index) => `<span>${index + 1}. ${step}</span>`).join("")}
    </div>
    <p>${plan.reason}</p>
  `;
}

function renderAgentFlow(items = []) {
  const node = $("agentFlow");
  if (!node) return;
  node.classList.remove("empty");
  node.innerHTML = items.map((item) => `
    <div class="agent-step">
      <strong>${item.name}</strong>
      <em>${item.status}</em>
      <span>${item.detail}</span>
    </div>
  `).join("");
}

function renderExercises(items) {
  $("exerciseList").classList.remove("empty");
  $("exerciseList").innerHTML = items.map((item) => `
    <div class="list-item">
      <strong>${item.name}</strong>
      <span>${item.category} / ${item.target} / 难度 ${item.difficulty}</span>
      <em>匹配度 ${item.match_score}</em>
      <small>${item.reason || ""}</small>
    </div>
  `).join("");
  $("exerciseSelect").innerHTML = items.map((item) => `<option value="${item.name}">${item.name}</option>`).join("");
}

function renderVenues(items = []) {
  const node = $("venueList");
  if (!node) return;
  let venues = normalizeVenueItems(items.length ? items : SHIJIAZHUANG_VENUES);
  if (state.venueFilterMode !== "all") {
    venues = venues.filter((item) => item.kind === state.venueFilterMode);
  }
  venues.sort((left, right) => {
    if (state.venueSortMode === "distance") return Number(left.distance_km ?? 999) - Number(right.distance_km ?? 999);
    if (state.venueSortMode === "crowd") return Number(left.crowd_index ?? 100) - Number(right.crowd_index ?? 100);
    if (state.venueSortMode === "density") return Number(right.facility_count || 1) - Number(left.facility_count || 1);
    return Number(right.match_score || 0) - Number(left.match_score || 0);
  });
  state.venueSource = venues;
  hydrateVenueHeader();
  renderVenueStats(venues);
  renderVenueMap(venues);
  node.classList.remove("empty");
  node.innerHTML = venues.slice(0, 12).map((item, index) => `
    <article class="venue-card venue-${item.tone || "blue"}" data-venue-index="${index}">
      <div class="venue-cover ${item.image_url ? "has-image" : ""}" ${item.image_url ? `style="--venue-img:url('${escapeCssUrl(item.image_url)}')"` : ""}>
        <i>${item.icon || "⌖"}</i>
        <span>${item.category}</span>
        <b>${item.facility_count || 1} 处</b>
      </div>
      <div class="venue-body">
        <div class="venue-card-title">
          <h3>${item.display_name || item.name}</h3>
          <button class="venue-open-btn" type="button" data-venue-index="${index}" aria-label="查看 ${item.display_name || item.name}">›</button>
        </div>
        <p class="venue-address">⌖ ${item.address || item.location || "石家庄市"}</p>
        <p class="venue-hours">◷ ${item.open_hours || "以现场公示为准"}</p>
        <div class="venue-meta">
          <span>⭐ ${item.rating || "4.6"}</span>
          <span>◇ ${item.distance || formatDistance(item.distance_km)}</span>
          <span class="crowd ${crowdTone(item.crowd_index)}">人流 ${item.crowd_index ?? "--"}</span>
        </div>
        <div class="venue-density-line">
          <span>密度</span>
          <i><b style="width:${Math.max(8, Math.min(100, Number(item.density_score || 0)))}%"></b></i>
          <strong>${Math.round(Number(item.density_score || 0))}</strong>
        </div>
        <small>${item.equipment || "综合运动设施"}</small>
        <em>${item.reason || "附近可达，综合环境指标较均衡"}</em>
        <button class="venue-detail-btn" type="button" data-venue-index="${index}">查看详情</button>
      </div>
    </article>
  `).join("") || `<div class="venue-empty">当前筛选没有匹配场馆，换个条件试试。</div>`;
  bindVenueCardEvents();
}

function normalizeVenueItems(items = []) {
  return items.map((item, index) => {
    const sport = item.sport_type || item.sport || "";
    const leisure = item.leisure_type || item.leisure || "";
    const category = item.category || sportLabel(sport) || leisureLabel(leisure);
    const coverImage = fallbackVenueImage(sport, leisure, category, item, index);
    return {
      ...item,
      category,
      display_name: displayVenueName(item.display_name || item.name, category),
      image_url: item.image_url || coverImage.url,
      image_source: item.image_source || coverImage.source,
      image_attribution: item.image_attribution || coverImage.attribution,
      image_is_fallback: !item.image_url,
      icon: item.icon || venueIcon(sport, leisure),
      tone: item.tone || venueTone(sport, leisure, index),
      kind: item.kind || (leisure === "sports_centre" ? "indoor" : "outdoor"),
      distance_km: item.distance_km ?? parseDistanceKm(item.distance),
      facility_count: Number(item.facility_count || 1),
      density_score: Number(item.density_score || 0),
      crowd_index: Number(item.crowd_index ?? 50),
      match_score: Number(item.match_score || 0),
      rating: item.rating || "4.6",
    };
  });
}

function displayVenueName(name = "", category = "运动场地") {
  const text = String(name || "").trim();
  if (!text) return `未命名${category}`;
  if (/(\s|^)\d{6,}$/.test(text) && /运动场地|跑道|体育中心|健身点|球场/.test(text)) {
    return `未命名${category}`;
  }
  return text;
}

function escapeCssUrl(value = "") {
  return String(value).replace(/['"\\()]/g, encodeURIComponent);
}

function fallbackVenueImage(sport = "", leisure = "", category = "", item = {}, index = 0) {
  const asset = (file) => ({
    url: `/static/assets/venues/${file}`,
    source: "",
    attribution: "项目本地场馆封面",
  });
  const text = [sport, leisure, category, item.name, item.display_name, item.address, item.location].filter(Boolean).join(" ");
  if (/篮球|basketball/i.test(text)) return asset("basketball.png");
  if (/足球|soccer|pitch/i.test(text)) return asset("soccer.png");
  if (/体育馆|体育中心|sports_centre|健身|fitness/i.test(text)) return asset(index % 2 ? "sports-center.png" : "fitness.png");
  const images = {
    soccer: {
      ...asset("soccer.png"),
    },
    basketball: {
      ...asset("basketball.png"),
    },
    running: {
      ...asset("fitness.png"),
    },
    track: {
      ...asset("fitness.png"),
    },
    fitness: {
      ...asset("sports-center.png"),
    },
    court: {
      ...asset(["soccer.png", "basketball.png", "fitness.png", "sports-center.png"][index % 4]),
    },
  };
  if (sport === "soccer") return images.soccer;
  if (sport === "basketball") return images.basketball;
  if (sport === "running" || leisure === "track") return images.running;
  if (leisure === "sports_centre" || leisure === "fitness_station") return images.fitness;
  return images.court;
}

function sportLabel(value = "") {
  const labels = {
    athletics: "田径场",
    badminton: "羽毛球场",
    basketball: "篮球场",
    climbing: "攀岩场",
    multi: "综合场",
    running: "跑道",
    soccer: "足球场",
    table_tennis: "乒乓球",
    tennis: "网球场",
    volleyball: "排球场",
  };
  return labels[value] || "";
}

function leisureLabel(value = "") {
  const labels = { pitch: "运动场地", track: "跑道", sports_centre: "体育中心", fitness_station: "健身点" };
  return labels[value] || "运动场所";
}

function venueIcon(sport = "", leisure = "") {
  if (sport === "basketball") return "🏀";
  if (sport === "soccer") return "⚽";
  if (sport === "tennis" || sport === "badminton" || sport === "table_tennis") return "🎾";
  if (sport === "running" || leisure === "track") return "🏃";
  if (leisure === "sports_centre") return "🏟";
  if (leisure === "fitness_station") return "💪";
  return "📍";
}

function venueTone(sport = "", leisure = "", index = 0) {
  if (leisure === "sports_centre") return "violet";
  if (sport === "basketball") return "orange";
  if (sport === "soccer") return "blue";
  if (sport === "running" || leisure === "track") return "teal";
  return ["purple", "green", "blue", "teal"][index % 4];
}

function parseDistanceKm(value) {
  const parsed = parseFloat(String(value || "").replace("km", ""));
  return Number.isFinite(parsed) ? parsed : null;
}

function formatDistance(value) {
  return Number.isFinite(Number(value)) ? `${Number(value).toFixed(1)}km` : "未知";
}

function renderVenueStats(venues = []) {
  if ($("venueTotalCount")) $("venueTotalCount").textContent = venues.length;
  const lowCrowd = venues.filter((item) => Number(item.crowd_index || 0) <= 35).length;
  if ($("venueLowCrowdCount")) $("venueLowCrowdCount").textContent = lowCrowd;
  const averageDensity = venues.length
    ? Math.round(venues.reduce((sum, item) => sum + Number(item.density_score || 0), 0) / venues.length)
    : 0;
  if ($("venueAverageDensity")) $("venueAverageDensity").textContent = averageDensity;
}

function venueGridKey(item) {
  return `${Math.round(Number(item.latitude) / 0.02)},${Math.round(Number(item.longitude) / 0.02)}`;
}

function buildVenueClusters(venues = []) {
  const groups = new Map();
  venues.forEach((item) => {
    if (!Number.isFinite(Number(item.latitude)) || !Number.isFinite(Number(item.longitude))) return;
    const key = venueGridKey(item);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  });
  return Array.from(groups.values()).map((group) => {
    const count = group.length;
    const avgCrowd = group.reduce((sum, item) => sum + Number(item.crowd_index || 0), 0) / count;
    const density = Math.max(...group.map((item) => Number(item.density_score || 0)));
    return {
      count,
      density,
      avgCrowd,
      lat: group.reduce((sum, item) => sum + Number(item.latitude), 0) / count,
      lon: group.reduce((sum, item) => sum + Number(item.longitude), 0) / count,
      sample: group.slice(0, 5),
    };
  });
}

function renderVenueMap(venues = []) {
  const node = $("venueMap");
  if (!node) return;
  const isVisible = node.offsetWidth > 0 && node.offsetHeight > 0;
  if (!isVisible && !state.venueMap) return;
  const mappable = venues.filter((item) => Number.isFinite(Number(item.latitude)) && Number.isFinite(Number(item.longitude)));
  const clusters = buildVenueClusters(mappable);
  if (!window.L) {
    node.innerHTML = clusters.slice(0, 8).map((cluster) => `
      <button class="map-fallback-point ${crowdTone(cluster.avgCrowd)}" type="button">
        ${cluster.count} 个场馆<small>密度 ${Math.round(cluster.density)} / 平均人流 ${Math.round(cluster.avgCrowd)}</small>
      </button>
    `).join("");
    return;
  }
  const center = mappable[0] ? [Number(mappable[0].latitude), Number(mappable[0].longitude)] : [38.047, 114.514];
  if (!state.venueMap) {
    state.venueMap = window.L.map(node, { zoomControl: true }).setView(center, 12);
    window.L.tileLayer("http://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}", {
      maxZoom: 18,
      subdomains: ["1", "2", "3", "4"],
      attribution: "OpenStreetMap",
    }).addTo(state.venueMap);
  }
  state.venueMarkers.forEach((marker) => marker.remove());
  state.venueMarkers = [];
  const userLatLng = state.userLocation
    ? [Number(state.userLocation.lat), Number(state.userLocation.lon)]
    : null;
  if (userLatLng && Number.isFinite(userLatLng[0]) && Number.isFinite(userLatLng[1])) {
    const userMarker = window.L.marker(userLatLng, {
      zIndexOffset: 1000,
      icon: window.L.divIcon({
        className: "user-location-marker",
        html: `<span></span><b>我在这里</b>`,
        iconSize: [96, 40],
        iconAnchor: [18, 34],
      }),
    }).addTo(state.venueMap);
    userMarker.bindPopup(`当前位置<br>精度约 ${state.userLocation.accuracy || "--"} 米`);
    state.venueMarkers.push(userMarker);
  }
  clusters.forEach((cluster) => {
    const tone = crowdTone(cluster.avgCrowd);
    const color = tone === "high" ? "#ef4444" : tone === "mid" ? "#f59e0b" : "#22c55e";
    const marker = window.L.circleMarker([cluster.lat, cluster.lon], {
      radius: Math.min(30, 8 + cluster.count * 1.8 + cluster.density / 12),
      color,
      fillColor: color,
      fillOpacity: 0.34,
      weight: 2,
    }).addTo(state.venueMap);
    marker.bindPopup(`
      <strong>该区域 ${cluster.count} 个场馆</strong><br>
      场馆密度：${Math.round(cluster.density)}<br>
      平均人流：${Math.round(cluster.avgCrowd)}<br>
      ${cluster.sample.map((item) => item.display_name || item.name).join("<br>")}
    `);
    state.venueMarkers.push(marker);
  });
  if (userLatLng && Number.isFinite(userLatLng[0]) && Number.isFinite(userLatLng[1])) {
    state.venueMap.setView(userLatLng, 14);
  } else if (clusters.length) {
    const bounds = window.L.latLngBounds(clusters.map((cluster) => [cluster.lat, cluster.lon]));
    state.venueMap.fitBounds(bounds.pad(0.18), { maxZoom: 13 });
  }
  setTimeout(() => state.venueMap?.invalidateSize(), 80);
  [260, 700].forEach((delay) => setTimeout(() => state.venueMap?.invalidateSize(), delay));
}

function hydrateVenueHeader() {
  const date = new Date();
  const week = ["星期日", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六"][date.getDay()];
  if ($("venueTemp")) $("venueTemp").textContent = Math.round(SHIJIAZHUANG_ENVIRONMENT.temperature);
  if ($("venueWeather")) $("venueWeather").textContent = `${SHIJIAZHUANG_ENVIRONMENT.weather} · AQI ${SHIJIAZHUANG_ENVIRONMENT.aqi}`;
  if ($("venueTime")) $("venueTime").textContent = date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false });
  if ($("venueDate")) $("venueDate").textContent = `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日 ${week}`;
}

function startVenueClock() {
  hydrateVenueHeader();
  if (state.venueClockTimer) return;
  state.venueClockTimer = setInterval(hydrateVenueHeader, 1000);
}

function bindVenueCardEvents() {
  document.querySelectorAll("[data-venue-index]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const index = Number(event.currentTarget.dataset.venueIndex);
      if (Number.isFinite(index)) openVenueDetail(state.venueSource[index]);
    });
  });
}

function openVenueDetail(venue) {
  if (!venue) return;
  $("reportModalTitle").textContent = venue.display_name || venue.name;
  $("reportModalMeta").textContent = `${venue.category} · ${venue.address || venue.location}`;
  $("reportModalBody").innerHTML = `
    <div class="venue-detail-modal">
      <div class="venue-detail-hero venue-${venue.tone || "blue"}">
        ${venue.image_url ? `<img src="${venue.image_url}" alt="${venue.display_name || venue.name}">` : ""}
        <span>${venue.icon || "⌖"}</span>
        <div>
          <strong>${venue.display_name || venue.name}</strong>
          <small>${venue.reason || "附近可达，综合环境指标较均衡"}</small>
        </div>
      </div>
      <div class="modal-grid">
        <div><strong>开放时间</strong><span>${venue.open_hours || "以现场公示为准"}</span></div>
        <div><strong>评分</strong><span>${venue.rating || "4.6"}</span></div>
        <div><strong>距离</strong><span>${venue.distance || formatDistance(venue.distance_km)}</span></div>
        <div><strong>人流指数</strong><span>${venue.crowd_index ?? "--"}</span></div>
        <div><strong>该区域场馆数</strong><span>${venue.facility_count || 1}</span></div>
        <div><strong>场馆密度</strong><span>${Math.round(Number(venue.density_score || 0))}</span></div>
      </div>
      <p class="modal-summary">设施：${venue.equipment}</p>
      ${venue.display_name !== venue.name ? `<p class="modal-summary">数据源编号：${venue.source_id || venue.name}</p>` : ""}
      <p class="modal-summary">环境：石家庄当前 ${SHIJIAZHUANG_ENVIRONMENT.weather}，约 ${Math.round(SHIJIAZHUANG_ENVIRONMENT.temperature)}°C，AQI ${SHIJIAZHUANG_ENVIRONMENT.aqi}。建议选择低到中等强度训练，敏感人群控制户外时长。</p>
      <div class="venue-nav-actions">
        <a class="venue-nav-btn" href="${navigationUrl(venue)}" target="_blank" rel="noopener">导航到这里</a>
      </div>
    </div>
  `;
  showReportModal();
}

function navigationUrl(venue) {
  const destLat = Number(venue.latitude);
  const destLon = Number(venue.longitude);
  if (!Number.isFinite(destLat) || !Number.isFinite(destLon)) return "https://uri.amap.com/";
  const name = encodeURIComponent(venue.display_name || venue.name || "推荐场馆");
  return `https://uri.amap.com/navigation?to=${destLon},${destLat},${name}&mode=walk&policy=1&callnative=1`;
}

function cycleVenueSort() {
  const order = ["match", "crowd", "distance", "density"];
  const labels = { match: "综合推荐⌄", crowd: "少人优先⌄", distance: "距离优先⌄", density: "密度优先⌄" };
  state.venueSortMode = order[(order.indexOf(state.venueSortMode) + 1) % order.length];
  if ($("venueSortBtn")) $("venueSortBtn").textContent = labels[state.venueSortMode];
  renderVenues(state.dashboard?.recommendations?.venues || state.venueSource);
}

function cycleVenueFilter() {
  const order = ["all", "indoor", "outdoor"];
  const labels = { all: "全部场馆", indoor: "室内场馆", outdoor: "户外场地" };
  state.venueFilterMode = order[(order.indexOf(state.venueFilterMode) + 1) % order.length];
  if ($("venueFilterBtn")) $("venueFilterBtn").textContent = labels[state.venueFilterMode];
  renderVenues(state.dashboard?.recommendations?.venues || state.venueSource);
}

function renderTips(items) {
  $("tipsList").classList.remove("empty");
  $("tipsList").innerHTML = items.map((item) => `
    <div class="list-item">
      <strong>${item.title}</strong>
      <span>${item.content}</span>
      <em>${item.tag}</em>
    </div>
  `).join("");
}

function html(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));
}

function profileFormData() {
  const levelMap = { beginner: "初级", intermediate: "进阶", advanced: "熟练" };
  const level = $("fitnessLevel")?.value || state.user?.fitness_level || "beginner";
  return {
    age: Number($("age")?.value || state.user?.age || 20),
    fitnessLevel: level,
    fitnessText: levelMap[level] || "新手",
    injuries: ($("injuries")?.value || state.user?.injuries || "暂无伤病史").trim() || "暂无伤病史",
    preference: ($("preference")?.value || state.user?.preference || "综合训练").trim() || "综合训练",
    location: ($("location")?.value || state.user?.location || "校园东区").trim() || "校园东区",
  };
}

function splitEquipment(value) {
  return String(value || "")
    .split(/[、,，/;；|]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .filter((item) => !["无", "徒手", "null", "None"].includes(item));
}

function uniqueItems(items) {
  const seen = new Set();
  return items.filter((item) => {
    const name = typeof item === "string" ? item : item.name;
    if (!name || seen.has(name)) return false;
    seen.add(name);
    return true;
  });
}

function buildProfileRecommendation(profile, dashboard) {
  const exercises = dashboard?.recommendations?.exercises || [];
  const hasKneeRisk = /膝关节|膝|半月板|髌|腿/.test(profile.injuries) && !/暂无|无/.test(profile.injuries);
  const isBeginner = profile.fitnessLevel === "beginner";
  const isIntermediate = profile.fitnessLevel === "intermediate";
  const likesGeneral = /综合训练|综合|全身/.test(profile.preference);
  const likesStrength = /力量|抗阻|增肌/.test(profile.preference);
  const isEast = /东区|東区|east/i.test(profile.location);
  const risks = [];
  const plans = [];
  const equipment = [];

  if (hasKneeRisk) {
    risks.push({ name: "避免跳跃、深蹲过重、跑跳类训练", reason: `${profile.injuries} 需要降低膝关节冲击和负重峰值。` });
    plans.push({ name: "低冲击有氧 + 核心稳定训练", reason: "用椭圆机、核心激活和稳定性练习替代高冲击跑跳。" });
    equipment.push(
      { name: "椭圆机", reason: "减少膝关节冲击，同时保留心肺训练效果。" },
      { name: "瑜伽垫", reason: "用于核心稳定、拉伸和康复类动作。" },
      { name: "弹力带", reason: "便于低负荷激活臀腿和膝周稳定肌群。" },
    );
  }

  if (isBeginner) {
    plans.push({ name: "基础适应训练", reason: "先建立动作控制、基础心肺和训练习惯。" });
    equipment.push(
      { name: "瑜伽垫", reason: "适合新手热身、核心和拉伸恢复。" },
      { name: "弹力带", reason: "低门槛阻力训练，便于控制强度。" },
      { name: "动感单车", reason: "强度可控，适合初级心肺适应。" },
    );
  }

  if (isIntermediate) {
    plans.push({ name: "力量 + 心肺组合训练", reason: "进阶阶段适合把抗阻训练和有氧训练组合提升。" });
    equipment.push(
      { name: "哑铃", reason: "支持渐进力量训练和复合动作。" },
      { name: "跑步机", reason: "用于心肺训练和可控速度训练。" },
      { name: "划船机", reason: "提升全身心肺和背部发力协同。" },
    );
  }

  if (likesGeneral) {
    plans.push({ name: "力量训练 + 有氧训练 + 拉伸恢复", reason: "综合训练偏好适合覆盖力量、心肺和恢复三个模块。" });
    equipment.push(
      { name: "哑铃", reason: "覆盖上肢、下肢和核心力量动作。" },
      { name: "跑步机", reason: "补充有氧能力和热身环节。" },
      { name: "拉伸垫", reason: "用于训练后的柔韧和恢复。" },
    );
  } else if (likesStrength) {
    plans.push({ name: "渐进抗阻训练", reason: "力量训练偏好适合从复合动作和可控负荷开始。" });
    equipment.push({ name: "哑铃", reason: "便于渐进抗阻和复合动作训练。" });
  }

  const venue = {
    name: isEast ? "校园东区健身房" : "综合体育馆",
    location: profile.location,
    reason: isEast ? "当前位置包含东区，优先匹配距离更近的东区健身房。" : "当前位置未命中东区，推荐设施更完整的综合体育馆。",
  };
  const apiEquipment = exercises.flatMap((item) => splitEquipment(item.equipment)).map((name) => ({
    name,
    reason: "来自后端动作推荐的器材补充。",
  }));
  if (!plans.length) plans.push({ name: exercises[0]?.name || "综合适应训练", reason: "依据当前画像和后端推荐结果生成。" });
  if (!equipment.length) equipment.push(...apiEquipment, { name: "瑜伽垫", reason: "通用热身、核心和拉伸器材。" });
  if (!risks.length) risks.push({ name: "暂无明显禁忌，注意热身、补水和训练后拉伸", reason: "未识别到高风险伤病关键词。" });

  return {
    risks: uniqueItems(risks).slice(0, 4),
    plans: uniqueItems(plans).slice(0, 4),
    equipment: uniqueItems(equipment).slice(0, 5),
    venues: [venue],
  };
}

function renderAiList(id, items, formatter) {
  const node = $(id);
  if (!node) return;
  node.innerHTML = items.map(formatter).join("");
}

function renderProfileAi(dashboard = state.dashboard, profileOverride = null) {
  const graphNode = document.querySelector("#profile #profileKnowledgeGraph");
  const profile = profileOverride || profileFormData();
  const model = buildProfileRecommendation(profile, dashboard);

  if ($("profileAiStatus")) {
    $("profileAiStatus").textContent = `${profile.fitnessText} / ${profile.preference} / ${profile.location}`;
  }
  if ($("profileKgStatus")) {
    $("profileKgStatus").textContent = "AI推荐推理图谱 · 用户输入 -> 风险评估 / 规则引擎 -> 推荐结果";
  }

  renderAiList("profileEquipmentList", model.equipment, (item, index) => `
    <span><i>${index + 1}</i>${html(item.name)}<em>${html(item.reason)}</em></span>
  `);
  renderAiList("profilePlanList", model.plans, (item, index) => `
    <span><i>${index + 1}</i>${html(item.name)}<em>${html(item.reason)}</em></span>
  `);
  renderAiList("profileRiskList", model.risks, (item, index) => `
    <span><i>${index + 1}</i>${html(item.name)}<em>${html(item.reason)}</em></span>
  `);
  renderAiList("profileVenueList", model.venues, (item, index) => `
    <span><i>${index + 1}</i>${html(item.name)}<em>${html(item.reason)}</em></span>
  `);
  renderProfileKnowledgeGraph(graphNode, { profile, model });
}

function renderProfileKnowledgeGraph(node, data) {
  if (!node) return;
  const profile = data?.profile || profileFormData();
  const model = data?.model || buildProfileRecommendation(profile, state.dashboard);
  const topRisk = model.risks?.[0] || {};
  const topPlan = model.plans?.[0] || {};
  const topEquipment = model.equipment?.[0] || {};
  const topVenue = model.venues?.[0] || {};
  const injuryText = profile.injuries && !/^暂无|无$/.test(profile.injuries) ? profile.injuries : "暂无明显伤病";
  const nodes = [
    { id: "age", label: "年龄", value: `${profile.age || 20}岁`, type: "info", x: 150, y: 92, w: 218, h: 58, reason: "用户输入层：年龄影响训练强度和恢复节奏。" },
    { id: "level", label: "体能水平", value: profile.fitnessText || "新手", type: "info", x: 150, y: 172, w: 218, h: 58, reason: "用户输入层：用于判断训练负荷和动作难度。" },
    { id: "injury", label: "伤病史", value: injuryText, type: "info", x: 150, y: 252, w: 218, h: 58, reason: "用户输入层：用于风险过滤和运动禁忌判断。" },
    { id: "pref", label: "运动偏好", value: profile.preference || "综合训练", type: "info", x: 150, y: 332, w: 218, h: 58, reason: "用户输入层：用于匹配力量与心肺组合训练。" },
    { id: "location", label: "当前位置", value: profile.location || "校园东区", type: "info", x: 150, y: 412, w: 218, h: 58, reason: "用户输入层：用于匹配附近场馆。" },
    { id: "riskModel", label: "风险评估模型", value: "伤病过滤 + 运动禁忌判断", type: "decision", x: 560, y: 150, w: 260, h: 74, reason: "AI决策层：把伤病史转化为风险提醒。" },
    { id: "ruleEngine", label: "健身规则引擎", value: "规则评分 + AI分析策略", type: "decision", x: 560, y: 280, w: 270, h: 74, reason: "AI决策层：综合体能、偏好和动作库生成推荐。" },
    { id: "generator", label: "推荐生成模块", value: topPlan.name || "综合适应训练", type: "module", x: 560, y: 410, w: 270, h: 74, reason: topPlan.reason || "AI决策层：根据规则评分生成最终训练组合。" },
    { id: "risk", label: "风险提醒", value: topRisk.name || "暂无明显禁忌，注意热身、补水和训练强度", type: "risk", x: 950, y: 145, w: 270, h: 78, reason: topRisk.reason || "结果输出层：展示画像对应的风险提醒。" },
    { id: "plan", label: "推荐方案", value: topPlan.name || "综合适应训练", type: "plan", x: 950, y: 280, w: 248, h: 74, reason: topPlan.reason || "结果输出层：展示最终推荐方案。" },
    { id: "equipment", label: "推荐器材", value: topEquipment.name || "瑜伽垫", type: "equipment", x: 950, y: 390, w: 230, h: 64, reason: topEquipment.reason || "结果输出层：由推荐方案继续关联器材。" },
    { id: "venue", label: "推荐场馆", value: topVenue.name || "综合体育馆", type: "venue", x: 950, y: 480, w: 248, h: 64, reason: topVenue.reason || "结果输出层：由推荐方案继续关联场馆。" },
  ];
  const byId = Object.fromEntries(nodes.map((item) => [item.id, item]));
  const edges = [
    ["age", "ruleEngine", "强度判断"],
    ["level", "ruleEngine", "难度匹配"],
    ["injury", "riskModel", "风险判断"],
    ["pref", "ruleEngine", "偏好匹配"],
    ["location", "generator", "场馆匹配"],
    ["riskModel", "risk", "提醒"],
    ["ruleEngine", "generator", "生成策略"],
    ["generator", "plan", "输出方案"],
    ["plan", "equipment", "关联器材"],
    ["plan", "venue", "匹配场馆"],
  ];
  const edgeMarkup = edges.map(([source, target, label]) => {
    const a = byId[source];
    const b = byId[target];
    const midX = (a.x + b.x) / 2;
    const midY = (a.y + b.y) / 2;
    const offset = Math.max(48, Math.abs(b.x - a.x) * 0.28);
    const d = Math.abs(b.x - a.x) < 40
      ? `M${a.x} ${a.y} L${b.x} ${b.y}`
      : `M${a.x} ${a.y} C${a.x + offset} ${a.y}, ${b.x - offset} ${b.y}, ${b.x} ${b.y}`;
    return `
      <path class="kg-flow-line" d="${d}" marker-end="url(#kgArrow)" />
      <path class="kg-flow-pulse" d="${d}" />
      <text x="${midX}" y="${midY - 7}">${html(label)}</text>
    `;
  }).join("");
  const nodeMarkup = nodes.map((item) => {
    const valueLines = splitGraphText(item.value, item.valueMax || 15, item.valueLineLimit || 2);
    const valueY = valueLines.length > 1 ? 6 : 15;
    const valueMarkup = valueLines.map((line, index) => `
        <tspan x="0" dy="${index === 0 ? 0 : 16}">${html(line)}</tspan>
      `).join("");
    return `
      <g class="kg-entity node-${item.type}" transform="translate(${item.x} ${item.y})" tabindex="0">
        <title>${html(`${item.label}\n类型：${nodeTypeLabel(item.type)}\n说明：${item.reason}`)}</title>
        <rect x="${-(item.w || 170) / 2}" y="${-(item.h || 56) / 2}" width="${item.w || 170}" height="${item.h || 56}" rx="14"></rect>
        <text class="kg-label" y="${valueLines.length > 1 ? -16 : -7}">${html(String(item.label).slice(0, 18))}</text>
        <text class="kg-value" y="${valueY}">${valueMarkup}</text>
      </g>
    `;
  }).join("");
  node.innerHTML = `
    <svg viewBox="0 0 1120 540" role="img">
      <defs>
        <filter id="profileKgGlow" x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="4" result="blur"></feGaussianBlur>
          <feMerge><feMergeNode in="blur"></feMergeNode><feMergeNode in="SourceGraphic"></feMergeNode></feMerge>
        </filter>
        <marker id="profileKgArrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z"></path>
        </marker>
      </defs>
      <g class="kg-layer-labels">
        <text x="150" y="42">用户输入层</text>
        <text x="560" y="42">AI决策层</text>
        <text x="950" y="42">结果输出层</text>
      </g>
      <g class="profile-kg-edges">${edgeMarkup.replaceAll("url(#kgArrow)", "url(#profileKgArrow)").replaceAll("url(#kgGlow)", "url(#profileKgGlow)")}</g>
      <g class="profile-kg-nodes">${nodeMarkup}</g>
    </svg>
  `;
}

function splitGraphText(value, maxLength = 15, maxLines = 2) {
  const text = String(value || "");
  if (text.length <= maxLength) return [text];
  const lines = [];
  for (let index = 0; index < text.length && lines.length < maxLines; index += maxLength) {
    lines.push(text.slice(index, index + maxLength));
  }
  return lines;
}

function nodeTypeLabel(type) {
  return {
    info: "基础信息",
    decision: "AI决策模型",
    module: "推荐模块",
    risk: "风险提醒",
    plan: "推荐方案",
    equipment: "推荐器材",
    venue: "场馆推荐",
  }[type] || "知识节点";
}

function renderReport(report) {
  const sessions = report.sessions || [];
  const rhythm = buildReportRhythm(report);
  const average = Number(report.average || 0);
  $("reportSummary").textContent = report.summary;
  $("reportRhythmSummary").textContent = `今日 ${rhythm.today} 次 · 本周 ${rhythm.week} 次 · 累计 ${rhythm.total} 次`;
  renderWeeklyRhythm(buildWeeklyRhythm(report));
  $("reportInsight").innerHTML = `
    <span><small>平均分</small><b>${average || "0"}</b></span>
    <span><small>优势动作</small><b>${cleanLabel(report.best_exercise, "未记录动作")}</b></span>
    <span><small>薄弱动作</small><b>${cleanLabel(report.weak_exercise, "未记录动作")}</b></span>
    <span><small>训练次数</small><b>${report.count || sessions.length || 0}</b></span>
  `;
  renderTrend(report.trend || []);
  $("sessionList").innerHTML = sessions.length ? sessions.map((item) => `
    <div class="report-session-item">
      <strong>${formatTime(item.created_at)} · ${cleanLabel(item.exercise_name)} · ${item.score} 分</strong>
      <span>${item.feedback || "动作表现稳定，继续保持节奏。"}</span>
      <em>+${item.points || 0} 积分 / ${item.duration || 0} 秒</em>
    </div>
  `).join("") : `<div class="report-session-item empty">暂无训练记录，完成一次体感关卡后生成训练明细。</div>`;
}

function renderWeeklyRhythm(items = []) {
  const node = $("weeklyRhythmChart");
  if (!node) return;
  const maxCount = Math.max(1, ...items.map((item) => Number(item.count || 0)));
  node.innerHTML = items.map((item) => {
    const count = Number(item.count || 0);
    const height = count ? Math.max(18, Math.round((count / maxCount) * 92)) : 8;
    return `
      <div class="rhythm-day ${item.isToday ? "today" : ""}">
        <span style="height:${height}px"></span>
        <b>${count}</b>
        <small>${item.isToday ? "今日" : item.label}</small>
      </div>
    `;
  }).join("");
}

function renderTrend(items) {
  const node = $("trendChart");
  if (!node) return;
  if (!items.length) {
    node.innerHTML = `<div class="empty">暂无趋势数据。</div>`;
    return;
  }
  node.innerHTML = items.map((item) => `
    <div class="trend-bar" title="${cleanLabel(item.exercise_name)} ${item.score}分">
      <span style="height:${item.score}%"></span>
      <b>${item.score}</b>
      <small>${String(item.created_at || "").slice(5, 16) || cleanLabel(item.exercise_name)}</small>
    </div>
  `).join("");
}

function renderBadges(items = []) {
  const node = $("badgeList");
  if (!node) return;
  node.classList.remove("empty");
  const earnedCount = items.filter((item) => item.earned).length;
  node.innerHTML = `
    <div class="badge-overview">已获得 ${earnedCount}/${items.length || 0} 枚徽章</div>
    ${items.map((item) => `
    <div class="badge-card ${item.earned ? "earned" : ""}">
      <strong>${item.icon || "★"} ${item.name}</strong>
      <span>${item.condition_text}</span>
      <i><span style="width:${item.earned ? 100 : 34}%"></span></i>
      <em>${item.earned ? `获得时间：${formatTime(item.earned_at)}` : `解锁奖励：${item.reward_points || 0} 积分`}</em>
    </div>
  `).join("")}`;
}

function renderPointLogs(items = []) {
  const node = $("pointLogList");
  if (!node) return;
  node.classList.remove("empty");
  node.innerHTML = items.length ? items.map((item) => `
    <div class="point-log-item">
      <strong>+${item.points_change} 积分</strong>
      <span>${item.description || item.source_type}</span>
      <em>${formatTime(item.created_at)} · 累计 ${item.total_points}</em>
    </div>
  `).join("") : "完成一次训练后生成积分流水。";
}

function renderLevels() {
  const node = $("levelSummary");
  if (!node) return;
  const currentLevel = Number(state.user?.level || 1);
  const currentPoints = Number(state.user?.points || 0);
  const levels = [
    { level: 1, title: "新手", min: 0, text: "完成基础体感训练并熟悉节奏" },
    { level: 2, title: "进阶", min: 120, text: "解锁更多训练关卡" },
    { level: 3, title: "熟练", min: 240, text: "保持连续训练节奏" },
    { level: 4, title: "达人", min: 360, text: "获得高级训练反馈" },
  ];
  node.classList.remove("empty");
  node.innerHTML = levels.map((item) => {
    const active = item.level === currentLevel;
    const reached = currentPoints >= item.min;
    return `
      <div class="level-row ${active ? "active" : ""} ${reached ? "reached" : ""}">
        <strong>Lv.${item.level} ${item.title}</strong>
        <span>${item.min} 积分解锁</span>
        <em>${active ? `当前等级，累计 ${currentPoints} 积分` : item.text}</em>
      </div>
    `;
  }).join("");
}

async function loadLevels() {
  renderLevels();
}

async function loadReportHistory() {
  const report = state.dashboard?.report;
  state.reportHistory = report ? [{
    report_type: $("reportTypeSelect")?.value || "weekly",
    session_count: report.count || 0,
    average_score: report.average || 0,
    weak_exercise: report.weak_exercise || "",
    summary: report.summary || "暂无报告",
    suggestion: report.suggestion || "",
    generated_at: new Date().toISOString().slice(0, 19).replace("T", " "),
  }] : [];
}

async function loadAgentLogs() {
  const node = $("agentLogList");
  if (!node) return;
  const items = state.dashboard?.agent_flow || [];
  node.classList.remove("empty");
  node.innerHTML = items.length ? items.map((item) => `
    <div class="agent-log-item">
      <strong>${item.name}</strong>
      <span>${item.detail}</span>
      <em>${item.status} · ${formatTime(new Date().toISOString())}</em>
    </div>
  `).join("") : "暂无智能体日志。";
}

function generateCurrentReport() {
  if (state.dashboard?.report) {
    openReportModal({
      ...state.dashboard.report,
      report_type: $("reportTypeSelect")?.value || "weekly",
      average_score: state.dashboard.report.average || 0,
      session_count: state.dashboard.report.count || 0,
      generated_at: new Date().toISOString().slice(0, 19).replace("T", " "),
    });
  }
}

async function loadExerciseLibrary() {
  const node = $("exerciseLibrary");
  if (!node) return;
  try {
    const data = await api("/api/exercises");
    node.classList.remove("empty");
    node.innerHTML = data.exercises.map((item) => `
      <article class="library-card">
        <strong>${item.name}</strong>
        <span>${item.category} / ${item.target}</span>
        <p>难度 ${item.difficulty}，器材：${item.equipment}</p>
        <small>${Object.entries(item.standard || {}).map(([key, value]) => `${key}: ${value}`).join("；")}</small>
      </article>
    `).join("");
  } catch (error) {
    node.textContent = "动作库暂时无法加载。";
  }
}

async function login() {
  try {
    const data = await api("/api/login", {
      method: "POST",
      body: JSON.stringify({ username: $("username").value, password: $("password").value }),
    });
    setUser(data.user);
    if (!isAdminUser()) await loadDashboard();
    showView(isAdminUser() ? "admin" : "dashboard");
  } catch (error) {
    toast(error.message);
  }
}

async function register() {
  try {
    const data = await api("/api/register", {
      method: "POST",
      body: JSON.stringify({
        username: $("username").value,
        password: $("password").value,
        nickname: $("nickname").value,
      }),
    });
    setUser(data.user);
    await loadDashboard();
    showView("dashboard");
  } catch (error) {
    toast(error.message);
  }
}

async function saveProfile() {
  if (!state.user) return toast("请先登录或注册");
  const submittedProfile = profileFormData();
  const data = await api("/api/profile", {
    method: "POST",
    body: JSON.stringify({
      user_id: state.user.id,
      age: $("age").value,
      fitness_level: $("fitnessLevel").value,
      injuries: $("injuries").value,
      preference: $("preference").value,
      location: $("location").value,
    }),
  });
  setUser(data.user);
  state.dashboard = data.dashboard;
  renderNotificationSummary(data.dashboard.notifications || []);
  renderExercises(data.dashboard.recommendations.exercises);
  renderVenues(data.dashboard.recommendations.venues);
  renderTips(data.dashboard.tips);
  renderProfileAi(data.dashboard, submittedProfile);
  renderReport(data.dashboard.report);
  $("profileSummary").textContent = data.dashboard.profile_summary;
}

async function submitSession() {
  if (!state.user) return toast("请先登录或注册");
  const gameScore = Math.min(100, 60 + state.game.score / 36 + state.game.bestCombo * 1.4);
  const score = Math.round(Math.max(state.poseScore, gameScore));
  const data = await api("/api/session", {
    method: "POST",
    body: JSON.stringify({
      user_id: state.user.id,
      exercise_name: state.selectedExercise || $("exerciseSelect").value,
      score,
      duration: $("durationInput").value,
    }),
  });
  persistPoseSnapshot();
  $("startGameBtn").textContent = "重新开始";
  $("startGameBtn").classList.remove("is-running");
  $("gameResult").innerHTML = `
    <strong>${data.score} 分，获得 ${data.game.points} 积分</strong>
    <p>${data.feedback}</p>
    <span>${data.game.unlocked.length ? `解锁：${data.game.unlocked.join("、")}` : "继续训练可解锁新关卡"}</span>
  `;
  state.user.points = data.game.total_points;
  state.user.level = data.game.level;
  setUser(state.user);
  await loadDashboard();
}

async function persistPoseSnapshot() {
  if (!state.user) return;
  try {
    await api("/api/pose/record", {
      method: "POST",
      body: JSON.stringify({
        user_id: state.user.id,
        exercise_name: state.selectedExercise || $("exerciseSelect").value,
        confidence: Number(($("poseConfidence").textContent || "0").replace("%", "")),
        stability_score: Number($("stabilityScore").textContent || 0),
        knee_angle: null,
        hip_angle: null,
        shoulder_balance: Number($("stabilityScore").textContent || 0),
        raw_landmarks_json: JSON.stringify({ source: state.modelReady ? "mediapipe" : "keyboard", score: state.poseScore }),
      }),
    });
  } catch (error) {
    console.warn("pose record skipped", error);
  }
}

function chooseExercise(name) {
  state.selectedExercise = name || state.selectedExercise;
  const select = $("exerciseSelect");
  if (select && name && ![...select.options].some((option) => option.value === name)) {
    select.add(new Option(name, name));
  }
  if (select && [...select.options].some((option) => option.value === name)) {
    select.value = name;
  }
  document.querySelectorAll(".game-card").forEach((card) => {
    card.classList.toggle("active", card.dataset.exercise === name);
  });
  showView("game");
  enterTraining(name);
}

function enterTraining(name) {
  stopCameraRecognition({ silent: true });
  state.selectedExercise = name || state.selectedExercise;
  const hub = $("trainingHub");
  const workspace = $("trainingWorkspace");
  if (hub) hub.hidden = true;
  if (workspace) workspace.hidden = false;
  const select = $("exerciseSelect");
  if (select && name && ![...select.options].some((option) => option.value === name)) {
    select.add(new Option(name, name));
  }
  if (select && name && [...select.options].some((option) => option.value === name)) {
    select.value = name;
  }
  updateTrainingModeText();
  state.game.running = false;
  state.game.poseDriven = false;
  state.game.playerLocked = false;
  state.game.finished = false;
  if (state.game.countdownId) {
    clearInterval(state.game.countdownId);
    state.game.countdownId = null;
  }
  state.game.timeLeft = Number($("durationInput").value) || 60;
  state.game.action = "待开始";
  $("currentAction").textContent = "待开始";
  $("timeLeft").textContent = state.game.timeLeft;
  $("startGameBtn").textContent = "开始";
  $("startGameBtn").classList.remove("is-running");
  drawGame();
}

function backToTrainingHub() {
  stopCameraRecognition({ silent: true });
  state.game.running = false;
  state.game.poseDriven = false;
  state.game.playerLocked = false;
  if (state.game.countdownId) {
    clearInterval(state.game.countdownId);
    state.game.countdownId = null;
  }
  const hub = $("trainingHub");
  const workspace = $("trainingWorkspace");
  workspace?.classList.remove("running-layout", "boxing-layout");
  if (workspace) workspace.hidden = true;
  if (hub) hub.hidden = false;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function resetMotionState() {
  state.latestLandmarks = null;
  state.lastPoseAt = 0;
  state.lastLandmarkAt = 0;
  state.lastPoseActionAt = 0;
  state.lastVideoTime = -1;
  state.poseScore = 70;
  state.poseStats = {
    frames: 0,
    totalScore: 0,
    bestScore: 0,
    reps: 0,
    targetReps: getExerciseRule().targetReps,
    lastRepAt: 0,
  };
  state.run.armSwing = 0;
  state.run.legSwing = 0;
  state.run.cadence = 0;
  state.run.lastStepAt = 0;
  state.run.lastStepSide = "";
  state.run.lastArmSide = "";
  state.run.status = "准备";
  state.boxing.leftArm = 0;
  state.boxing.rightArm = 0;
  state.boxing.crouch = 0;
  state.boxing.status = "准备";
  $("poseConfidence").textContent = "0%";
  $("stabilityScore").textContent = "0";
  $("scoreValue").textContent = state.poseScore;
  $("scoreInput").value = state.poseScore;
}

function resetGameSession() {
  if (state.game.loopId) {
    cancelAnimationFrame(state.game.loopId);
    state.game.loopId = null;
  }
  if (state.game.countdownId) {
    clearInterval(state.game.countdownId);
    state.game.countdownId = null;
  }
  state.game.running = false;
  state.game.finished = false;
  state.game.poseDriven = false;
  state.game.score = 0;
  state.game.combo = 0;
  state.game.bestCombo = 0;
  state.game.timeLeft = Number($("durationInput").value) || 60;
  state.game.targets = [];
  state.game.particles = [];
  state.game.lastSpawn = 0;
  state.game.lastFrame = performance.now();
  state.game.staticFrameTime = state.game.lastFrame;
  state.game.inputFlash = null;
  state.game.action = "准备";
  resetMotionState();
}

function startCountdown() {
  if (state.game.countdownId) clearInterval(state.game.countdownId);
  state.game.countdownId = setInterval(() => {
    if (!state.game.running || state.game.finished) return;
    state.game.timeLeft = Math.max(0, state.game.timeLeft - 1);
    updateHud();
    if (state.game.timeLeft <= 0) finishGame();
  }, 1000);
}

async function startGame() {
  stopCameraRecognition({ silent: true });
  resetGameSession();
  const rule = getExerciseRule();
  state.game.running = true;
  state.game.poseActive = true;
  state.game.poseDriven = true;
  state.game.playerLocked = false;
  state.game.action = rule.startPrompt;
  $("startGameBtn").textContent = "训练中";
  $("startGameBtn").classList.add("is-running");
  $("currentAction").textContent = rule.startPrompt;
  $("timeLeft").textContent = Math.ceil(state.game.timeLeft);
  $("gameResult").textContent = `训练开始：${rule.startPrompt}。小人会根据摄像头识别到的关键点实时同步动作。`;
  drawGame();
  startCountdown();
  await openCamera();
}

function updateTrainingModeTextLegacy() {
  const running = isRunningMode();
  const layout = $("trainingWorkspace");
  const title = document.querySelector(".game-panel h2");
  const intro = document.querySelector(".game-panel .stage-top p");
  const overlay = document.querySelectorAll(".stage-overlay span");
  if (title) title.textContent = running ? "跑步与快走体感训练" : "MediaPipe 体感训练关卡";
  if (intro) {
    intro.textContent = running
      ? "摄像头识别摆臂、抬膝和节奏状态，并根据真实动作计算训练得分。"
      : "摄像头识别抬手、挥拳、下蹲和深蹲姿态；也可用键盘演示答辩流程。";
  }
  if (overlay.length >= 3) {
    overlay[0].textContent = running ? "摆臂节奏" : "左挥击 A / ←";
    overlay[1].textContent = running ? "抬膝步频" : "下蹲 S / ↓";
    overlay[2].textContent = running ? "能量目标" : "右挥击 D / →";
  }
  setStatus(
    running
      ? "跑步模式：开启 MediaPipe 后，根据摆臂、抬膝和步频判断训练状态。"
      : "键盘可先演示；摄像头模式使用 MediaPipe Pose Landmarker。",
  );
}

function updateTrainingModeText() {
  const running = isRunningMode();
  const boxing = isBoxingMode();
  const layout = $("trainingWorkspace");
  const title = document.querySelector(".game-panel h2");
  const intro = document.querySelector(".game-panel .stage-top p");
  const overlay = document.querySelectorAll(".stage-overlay span");

  if (layout) {
    layout.classList.toggle("running-layout", running);
    layout.classList.toggle("boxing-layout", boxing);
  }
  if (title) title.textContent = running ? "跑步与快走体感训练" : boxing ? "拳击与踢击体感训练" : "MediaPipe 体感训练关卡";
  if (intro) {
    intro.textContent = running
      ? "摄像头识别摆臂、抬膝和节奏状态，并根据真实动作计算训练得分。"
      : boxing
        ? "摄像头识别左右挥拳和下蹲闪避，小人会跟随你的身体动作完成拳击训练。"
        : "摄像头识别抬手、挥拳、下蹲和深蹲姿态；也可用键盘演示答辩流程。";
  }
  if (overlay.length >= 3) {
    overlay[0].textContent = running ? "摆臂节奏" : boxing ? "左拳识别" : "左挥击 A / ←";
    overlay[1].textContent = running ? "抬膝步频" : boxing ? "下蹲闪避" : "下蹲 S / ↓";
    overlay[2].textContent = running ? "能量目标" : boxing ? "右拳识别" : "右挥击 D / →";
  }
  setStatus(
    running
      ? "跑步模式：开启 MediaPipe 后，根据摆臂、抬膝和步频判断训练状态。"
      : boxing
        ? "拳击模式：开启 MediaPipe 后，根据左右手出拳和下蹲闪避判断动作。"
        : "键盘可先演示；摄像头模式使用 MediaPipe Pose Landmarker。",
  );
}

function loopGame(now) {
  drawGame(now);
  if (state.game.running) state.game.loopId = requestAnimationFrame(loopGame);
}

function drawGame(now = performance.now()) {
  const canvas = $("gameCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  const motionlessScene = state.game.playerLocked || state.game.poseDriven;
  const renderTime = motionlessScene ? (state.game.staticFrameTime || state.game.lastFrame || now) : now;
  const delta = motionlessScene ? 0 : Math.min(0.05, (now - state.game.lastFrame) / 1000 || 0.016);
  state.game.lastFrame = now;

  drawWorld(ctx, w, h, renderTime);
  if (state.game.running && !motionlessScene) {
    state.game.timeLeft = Math.max(0, state.game.timeLeft - delta);
    if (now - state.game.lastSpawn > Math.max(560, 1260 - (state.user?.level || 1) * 32)) {
      spawnTarget();
      state.game.lastSpawn = now;
    }
    updateTargets(delta);
    if (state.game.timeLeft <= 0) finishGame();
  }
  if (state.game.running && !motionlessScene) drawTargets(ctx, w, h);
  drawPlayer(ctx, w, h, renderTime);
  if (!motionlessScene) drawParticles(ctx, delta);
  updateHud();
}

function drawWorld(ctx, w, h, now) {
  const cover = getSelectedExerciseCover();
  if (cover?.complete && cover.naturalWidth) {
    drawCoverImage(ctx, cover, w, h);
    ctx.fillStyle = "rgba(6, 16, 31, .18)";
    ctx.fillRect(0, 0, w, h);
    return;
  }

  const sky = ctx.createLinearGradient(0, 0, 0, h);
  sky.addColorStop(0, "#f7b65d");
  sky.addColorStop(0.32, "#cc562e");
  sky.addColorStop(1, "#10151e");
  ctx.fillStyle = sky;
  ctx.fillRect(0, 0, w, h);

  ctx.fillStyle = "#4b1f22";
  drawPolygon(ctx, [[0, h * .42], [w * .09, h * .26], [w * .18, h * .37], [w * .29, h * .20], [w * .42, h * .43], [w * .55, h * .24], [w * .69, h * .41], [w * .82, h * .22], [w, h * .34], [w, h], [0, h]]);
  ctx.fillStyle = "#733020";
  drawPolygon(ctx, [[0, h * .58], [w * .14, h * .44], [w * .27, h * .54], [w * .42, h * .40], [w * .56, h * .56], [w * .7, h * .45], [w * .86, h * .55], [w, h * .44], [w, h], [0, h]]);

  const road = ctx.createLinearGradient(0, h * .38, 0, h);
  road.addColorStop(0, "rgba(34, 25, 29, .75)");
  road.addColorStop(1, "rgba(8, 13, 20, .96)");
  ctx.fillStyle = road;
  drawPolygon(ctx, [[w * .47, h * .40], [w * .53, h * .40], [w * .86, h], [w * .14, h]]);

  ctx.strokeStyle = "rgba(255,255,255,.34)";
  ctx.lineWidth = Math.max(1.5, w / 430);
  for (let lane = -2; lane <= 2; lane += 1) {
    ctx.beginPath();
    ctx.moveTo(w * .5 + lane * w * .015, h * .42);
    ctx.lineTo(w * .5 + lane * w * .105, h);
    ctx.stroke();
  }

  ctx.fillStyle = "rgba(255,255,255,.2)";
  for (let i = 0; i < 17; i += 1) {
    const y = ((now / 12 + i * 54) % (h * .86)) + h * .12;
    const scale = y / h;
    ctx.fillRect(w * .5 - 2, y, 4 + scale * 8, 12 + scale * 36);
  }

  const beam = ctx.createLinearGradient(w * .38, 0, w * .6, h);
  beam.addColorStop(0, "rgba(49, 217, 255, .62)");
  beam.addColorStop(.52, "rgba(49, 217, 255, .16)");
  beam.addColorStop(1, "rgba(49, 217, 255, 0)");
  ctx.fillStyle = beam;
  drawPolygon(ctx, [[w * .38, 0], [w * .54, 0], [w * .63, h], [w * .42, h]]);
}

function drawCoverImage(ctx, img, w, h) {
  const scale = Math.max(w / img.naturalWidth, h / img.naturalHeight);
  const sw = w / scale;
  const sh = h / scale;
  const sx = (img.naturalWidth - sw) / 2;
  const sy = (img.naturalHeight - sh) / 2;
  ctx.drawImage(img, sx, sy, sw, sh, 0, 0, w, h);
}

function getSelectedExerciseCover() {
  const type = getExerciseType();
  if (type === "running") return state.assets.runningCover;
  if (type === "boxing") return state.assets.boxingCover;
  if (type === "jumping") return state.assets.jumpingCover;
  if (type === "stretch") return state.assets.stretchCover;
  if (type === "core") return state.assets.coreCover;
  if (type === "squat") return state.assets.squatCover;
  return state.assets.runningCover;

  const value = state.selectedExercise || "";
  if (value.includes("开合") || value.includes("跳")) return state.assets.jumpingCover;
  if (value.includes("拉伸")) return state.assets.stretchCover;
  if (value.includes("平板") || value.includes("支撑")) return state.assets.coreCover;
  if (value.includes("深蹲")) return state.assets.squatCover;
  return state.assets.squatCover;
}

function drawRunningWorld(ctx, w, h, now) {
  const bg = state.assets.runningCover;
  if (bg?.complete && bg.naturalWidth) {
    drawCoverImage(ctx, bg, w, h);
  } else {
    const sky = ctx.createLinearGradient(0, 0, 0, h);
    sky.addColorStop(0, "#69cfff");
    sky.addColorStop(.45, "#baf1ff");
    sky.addColorStop(1, "#2b7a4b");
    ctx.fillStyle = sky;
    ctx.fillRect(0, 0, w, h);
  }

  ctx.fillStyle = "rgba(6, 16, 31, .18)";
  ctx.fillRect(0, 0, w, h);

  ctx.fillStyle = "rgba(75, 218, 255, .55)";
  for (let i = 0; i < 9; i += 1) {
    const y = ((now / 8 + i * 88) % (h * .74)) + h * .24;
    const width = 34 + (y / h) * 60;
    ctx.beginPath();
    ctx.moveTo(w * .5 - width * .5, y);
    ctx.lineTo(w * .5, y + 18);
    ctx.lineTo(w * .5 + width * .5, y);
    ctx.lineTo(w * .5 + width * .32, y + 28);
    ctx.lineTo(w * .5, y + 12);
    ctx.lineTo(w * .5 - width * .32, y + 28);
    ctx.closePath();
    ctx.fill();
  }
}

function drawBoxingWorld(ctx, w, h, now) {
  const bg = state.assets.boxingCover;
  if (bg?.complete && bg.naturalWidth) {
    const scale = Math.max(w / bg.naturalWidth, h / bg.naturalHeight);
    const sw = w / scale;
    const sh = h / scale;
    const sx = (bg.naturalWidth - sw) / 2;
    const sy = (bg.naturalHeight - sh) * 0.42;
    ctx.drawImage(bg, sx, sy, sw, sh, 0, 0, w, h);
  } else {
    const arena = ctx.createLinearGradient(0, 0, 0, h);
    arena.addColorStop(0, "#07142a");
    arena.addColorStop(.55, "#111827");
    arena.addColorStop(1, "#210710");
    ctx.fillStyle = arena;
    ctx.fillRect(0, 0, w, h);
  }

  ctx.fillStyle = "rgba(4, 9, 18, .22)";
  ctx.fillRect(0, 0, w, h);

  const coverPatch = ctx.createRadialGradient(w * .5, h * .58, h * .08, w * .5, h * .58, h * .28);
  coverPatch.addColorStop(0, "rgba(14, 23, 39, .92)");
  coverPatch.addColorStop(.58, "rgba(14, 23, 39, .68)");
  coverPatch.addColorStop(1, "rgba(14, 23, 39, 0)");
  ctx.fillStyle = coverPatch;
  ctx.fillRect(w * .24, h * .26, w * .52, h * .52);

  ctx.strokeStyle = "rgba(255, 55, 88, .76)";
  ctx.lineWidth = Math.max(2, w * .004);
  for (let i = 0; i < 5; i += 1) {
    const y = h * (.30 + i * .10);
    ctx.beginPath();
    ctx.moveTo(w * .08, y);
    ctx.lineTo(w * .92, y);
    ctx.stroke();
  }

  const pulse = 0.55 + Math.sin(now / 220) * 0.18;
  ctx.fillStyle = `rgba(255, 213, 74, ${pulse})`;
  ctx.beginPath();
  ctx.arc(w * .78, h * .44, h * .05, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = "rgba(255,255,255,.7)";
  ctx.stroke();
}

function drawPolygon(ctx, points) {
  ctx.beginPath();
  points.forEach(([x, y], index) => (index ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
  ctx.closePath();
  ctx.fill();
}

function spawnTarget() {
  if (isRunningMode()) {
    const types = ["energy", "pace"];
    const type = types[Math.floor(Math.random() * types.length)];
    const lanes = [0.34, 0.5, 0.66];
    state.game.targets.push({
      type,
      x: lanes[Math.floor(Math.random() * lanes.length)],
      y: 0.34,
      z: 0,
      size: type === "energy" ? 0.08 : 0.07,
      speed: 0.44 + Math.random() * 0.12 + (state.user?.level || 1) * 0.007,
      hit: false,
    });
    return;
  }

  const types = ["left", "right", "duck"];
  const type = types[Math.floor(Math.random() * types.length)];
  const xMap = { left: 0.34, right: 0.66, duck: 0.5 };
  state.game.targets.push({
    type,
    x: xMap[type],
    y: 0.31,
    z: 0,
    size: type === "duck" ? 0.15 : 0.085,
    speed: 0.48 + Math.random() * 0.13 + (state.user?.level || 1) * 0.009,
    hit: false,
  });
}

function updateTargets(delta) {
  state.game.targets.forEach((target) => {
    target.z += target.speed * delta;
    target.y = 0.31 + target.z * 0.54;
  });
  state.game.targets = state.game.targets.filter((target) => {
    if (target.hit) return false;
    if (target.z > 1.06) {
      state.game.combo = 0;
      return false;
    }
    return true;
  });
}

function drawTargets(ctx, w, h) {
  state.game.targets.forEach((target) => drawOneTarget(ctx, w, h, target));
}

function drawOneTarget(ctx, w, h, target) {
  const scale = 0.65 + target.z * 1.9;
  const x = w * target.x + (target.x - 0.5) * target.z * w * 0.2;
  const y = h * target.y;
  const radius = h * target.size * scale;

  if (target.type === "energy" || target.type === "pace") {
    const gradient = ctx.createRadialGradient(x - radius * .28, y - radius * .36, radius * .1, x, y, radius);
    gradient.addColorStop(0, "#ffffff");
    gradient.addColorStop(.32, target.type === "energy" ? "#ffe78a" : "#9bf4ff");
    gradient.addColorStop(1, target.type === "energy" ? "#ff9d16" : "#2386ff");
    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "rgba(255,255,255,.8)";
    ctx.lineWidth = Math.max(2, radius * .08);
    ctx.stroke();
    ctx.fillStyle = "#ffffff";
    ctx.font = `${Math.max(18, radius * .52)}px Microsoft YaHei`;
    ctx.textAlign = "center";
    ctx.fillText(target.type === "energy" ? "⚡" : "↟", x, y + radius * .18);
    return;
  }

  if (target.type === "duck") {
    ctx.fillStyle = "rgba(255, 95, 88, .23)";
    ctx.strokeStyle = "#ffd0cc";
    ctx.lineWidth = Math.max(2, radius * .05);
    roundedRect(ctx, x - radius * 1.8, y - radius * .65, radius * 3.6, radius * 1.3, radius * .2);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = "#ffe5e2";
    ctx.font = `${Math.max(16, radius * .35)}px Microsoft YaHei`;
    ctx.textAlign = "center";
    ctx.fillText("下蹲", x, y + radius * .12);
    return;
  }

  const gradient = ctx.createRadialGradient(x - radius * .3, y - radius * .4, radius * .1, x, y, radius);
  gradient.addColorStop(0, "#ffffff");
  gradient.addColorStop(.34, target.type === "left" ? "#88eaff" : "#ffe18b");
  gradient.addColorStop(1, target.type === "left" ? "#2875ff" : "#ff8a38");
  ctx.fillStyle = gradient;
  ctx.beginPath();
  ctx.arc(x, y, radius, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = "rgba(255,255,255,.76)";
  ctx.lineWidth = Math.max(2, radius * .07);
  ctx.stroke();
  ctx.fillStyle = "#10202c";
  ctx.font = `${Math.max(16, radius * .42)}px Microsoft YaHei`;
  ctx.textAlign = "center";
  ctx.fillText(target.type === "left" ? "左" : "右", x, y + radius * .15);
}

function drawPlayer(ctx, w, h, now) {
  if (state.game.poseDriven) {
    if (state.latestLandmarks && performance.now() - state.lastPoseAt < 900 && drawTrackedPosePlayer(ctx, w, h, state.latestLandmarks)) {
      return;
    }
    drawStaticPlayer(ctx, w, h);
    return;
  }

  if (state.game.playerLocked) {
    drawStaticPlayer(ctx, w, h);
    return;
  }

  if (state.latestLandmarks && now - state.lastPoseAt < 900 && drawTrackedPosePlayer(ctx, w, h, state.latestLandmarks)) {
    return;
  }

  drawGenericPlayer(ctx, w, h, now);
}

function drawStaticPlayer(ctx, w, h) {
  const cx = w * .56;
  const headY = h * .36;
  const shoulderY = h * .50;
  const hipY = h * .68;
  const segments = [
    [[cx, headY + h * .075], [cx, hipY]],
    [[cx, shoulderY], [cx - w * .11, h * .60]],
    [[cx, shoulderY], [cx + w * .11, h * .60]],
    [[cx, hipY], [cx - w * .085, h * .84]],
    [[cx, hipY], [cx + w * .085, h * .84]],
  ];

  ctx.save();
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.shadowColor = "rgba(255,255,255,.38)";
  ctx.shadowBlur = 18;
  ctx.strokeStyle = "rgba(47,108,246,.9)";
  ctx.lineWidth = Math.max(16, w * .024);
  for (const [from, to] of segments) {
    ctx.beginPath();
    ctx.moveTo(from[0], from[1]);
    ctx.lineTo(to[0], to[1]);
    ctx.stroke();
  }
  ctx.strokeStyle = "#f8fbff";
  ctx.lineWidth = Math.max(8, w * .014);
  for (const [from, to] of segments) {
    ctx.beginPath();
    ctx.moveTo(from[0], from[1]);
    ctx.lineTo(to[0], to[1]);
    ctx.stroke();
  }

  const headRadius = h * .055;
  const head = ctx.createRadialGradient(cx - w * .018, headY - h * .014, 2, cx, headY, headRadius);
  head.addColorStop(0, "#ffffff");
  head.addColorStop(1, "#dfe8f7");
  ctx.fillStyle = head;
  ctx.strokeStyle = "rgba(47,108,246,.9)";
  ctx.lineWidth = Math.max(6, w * .01);
  ctx.beginPath();
  ctx.arc(cx, headY, headRadius, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  ctx.restore();
}

function drawGenericPlayer(ctx, w, h, now) {
  const flash = state.game.inputFlash;
  const fresh = flash && now - flash.time < 180;
  const pulse = fresh ? 1 : 0.82 + Math.sin(now / 420) * 0.08;
  const crouch = flash?.action === "duck" && fresh ? h * .08 : 0;
  const cx = w * .5;
  const headY = h * .34 + crouch;
  const shoulderY = h * .48 + crouch;
  const hipY = h * .66 + crouch;
  const leftHandY = flash?.action === "left" && fresh ? h * .33 : h * .58;
  const rightHandY = flash?.action === "right" && fresh ? h * .33 : h * .58;
  const leftFootX = cx - w * .09;
  const rightFootX = cx + w * .09;

  ctx.save();
  ctx.globalAlpha = pulse;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.shadowColor = "rgba(255,255,255,.48)";
  ctx.shadowBlur = 18;
  ctx.strokeStyle = "#f7fbff";
  ctx.lineWidth = Math.max(11, w * .018);

  ctx.beginPath();
  ctx.moveTo(cx, headY + h * .075);
  ctx.lineTo(cx, hipY);
  ctx.moveTo(cx, shoulderY);
  ctx.lineTo(cx - w * .12, leftHandY);
  ctx.moveTo(cx, shoulderY);
  ctx.lineTo(cx + w * .12, rightHandY);
  ctx.moveTo(cx, hipY);
  ctx.lineTo(leftFootX, h * .84 - crouch * .4);
  ctx.moveTo(cx, hipY);
  ctx.lineTo(rightFootX, h * .84 - crouch * .4);
  ctx.stroke();

  const head = ctx.createRadialGradient(cx - w * .018, headY - h * .014, 2, cx, headY, h * .055);
  head.addColorStop(0, "#ffffff");
  head.addColorStop(1, "#dfe8f7");
  ctx.fillStyle = head;
  ctx.beginPath();
  ctx.arc(cx, headY, h * .055, 0, Math.PI * 2);
  ctx.fill();

  ctx.shadowBlur = 0;
  ctx.fillStyle = "rgba(47, 108, 246, .9)";
  for (const [x, y] of [[cx - w * .12, leftHandY], [cx + w * .12, rightHandY], [leftFootX, h * .84 - crouch * .4], [rightFootX, h * .84 - crouch * .4]]) {
    ctx.beginPath();
    ctx.arc(x, y, Math.max(5, w * .008), 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

function drawTrackedPosePlayer(ctx, w, h, landmarks) {
  const point = (index, minVisibility = 0.35) => {
    const point = landmarks[index];
    if (!point || point.visibility < minVisibility) return null;
    return point;
  };

  const leftShoulder = point(11, 0.5);
  const rightShoulder = point(12, 0.5);
  const leftHip = point(23, 0.45);
  const rightHip = point(24, 0.45);
  if (!leftShoulder || !rightShoulder || !leftHip || !rightHip) return false;

  const leftElbow = point(13);
  const rightElbow = point(14);
  const leftWrist = point(15);
  const rightWrist = point(16);
  const leftKnee = point(25);
  const rightKnee = point(26);
  const leftAnkle = point(27);
  const rightAnkle = point(28);
  const nose = point(0);

  const shoulderMid = midpoint(leftShoulder, rightShoulder);
  const hipMid = midpoint(leftHip, rightHip);
  const rawAngle = (a, b, fallback) => (a && b ? Math.atan2((b.y - a.y) * h, (b.x - a.x) * w) : fallback);
  const endPoint = (from, angleValue, length) => [
    from[0] + Math.cos(angleValue) * length,
    from[1] + Math.sin(angleValue) * length,
  ];

  const shoulderAngle = rawAngle(leftShoulder, rightShoulder, 0);
  const hipAngle = rawAngle(leftHip, rightHip, shoulderAngle);
  const torsoAngle = rawAngle(shoulderMid, hipMid, Math.PI / 2);
  const baseX = w * 0.56 + clamp((shoulderMid.x - 0.5) * w * 0.30, -w * 0.10, w * 0.10);
  const baseY = h * 0.48 + clamp((shoulderMid.y - 0.45) * h * 0.35, -h * 0.08, h * 0.12);

  const shoulderWidth = w * 0.18;
  const hipWidth = w * 0.12;
  const torsoLength = h * 0.20;
  const upperArm = h * 0.145;
  const lowerArm = h * 0.145;
  const upperLeg = h * 0.18;
  const lowerLeg = h * 0.18;
  const headRadius = Math.max(18, h * 0.055);

  const shoulderCenter = [baseX, baseY];
  const hipCenter = endPoint(shoulderCenter, torsoAngle, torsoLength);
  const shoulderVector = [Math.cos(shoulderAngle), Math.sin(shoulderAngle)];
  const hipVector = [Math.cos(hipAngle), Math.sin(hipAngle)];
  const leftShoulderJoint = [shoulderCenter[0] - shoulderVector[0] * shoulderWidth / 2, shoulderCenter[1] - shoulderVector[1] * shoulderWidth / 2];
  const rightShoulderJoint = [shoulderCenter[0] + shoulderVector[0] * shoulderWidth / 2, shoulderCenter[1] + shoulderVector[1] * shoulderWidth / 2];
  const leftHipJoint = [hipCenter[0] - hipVector[0] * hipWidth / 2, hipCenter[1] - hipVector[1] * hipWidth / 2];
  const rightHipJoint = [hipCenter[0] + hipVector[0] * hipWidth / 2, hipCenter[1] + hipVector[1] * hipWidth / 2];

  const leftElbowJoint = endPoint(leftShoulderJoint, rawAngle(leftShoulder, leftElbow, 2.18), upperArm);
  const leftHand = endPoint(leftElbowJoint, rawAngle(leftElbow, leftWrist, 2.05), lowerArm);
  const rightElbowJoint = endPoint(rightShoulderJoint, rawAngle(rightShoulder, rightElbow, 0.96), upperArm);
  const rightHand = endPoint(rightElbowJoint, rawAngle(rightElbow, rightWrist, 1.10), lowerArm);
  const leftKneeJoint = endPoint(leftHipJoint, rawAngle(leftHip, leftKnee, 1.76), upperLeg);
  const leftFoot = endPoint(leftKneeJoint, rawAngle(leftKnee, leftAnkle, 1.58), lowerLeg);
  const rightKneeJoint = endPoint(rightHipJoint, rawAngle(rightHip, rightKnee, 1.38), upperLeg);
  const rightFoot = endPoint(rightKneeJoint, rawAngle(rightKnee, rightAnkle, 1.58), lowerLeg);

  const neck = endPoint(shoulderCenter, torsoAngle + Math.PI, h * 0.08);
  const noseAngle = rawAngle(shoulderMid, nose, torsoAngle + Math.PI);
  const headX = neck[0] + Math.cos(noseAngle) * h * 0.045;
  const headY = neck[1] + Math.sin(noseAngle) * h * 0.045;
  const segments = [
    [neck, hipCenter],
    [leftShoulderJoint, rightShoulderJoint],
    [leftHipJoint, rightHipJoint],
    [leftShoulderJoint, leftElbowJoint],
    [leftElbowJoint, leftHand],
    [rightShoulderJoint, rightElbowJoint],
    [rightElbowJoint, rightHand],
    [leftHipJoint, leftKneeJoint],
    [leftKneeJoint, leftFoot],
    [rightHipJoint, rightKneeJoint],
    [rightKneeJoint, rightFoot],
  ];

  ctx.save();
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.shadowColor = "rgba(47,108,246,.82)";
  ctx.shadowBlur = 20;
  ctx.strokeStyle = "rgba(47,108,246,.96)";
  ctx.lineWidth = Math.max(16, w * .024);
  for (const [a, b] of segments) {
    ctx.beginPath();
    ctx.moveTo(a[0], a[1]);
    ctx.lineTo(b[0], b[1]);
    ctx.stroke();
  }
  ctx.strokeStyle = "rgba(255,255,255,.96)";
  ctx.lineWidth = Math.max(8, w * .014);
  for (const [a, b] of segments) {
    ctx.beginPath();
    ctx.moveTo(a[0], a[1]);
    ctx.lineTo(b[0], b[1]);
    ctx.stroke();
  }

  const head = ctx.createRadialGradient(headX - headRadius * .3, headY - headRadius * .35, 2, headX, headY, headRadius);
  head.addColorStop(0, "#ffffff");
  head.addColorStop(1, "#dfe8f7");
  ctx.fillStyle = head;
  ctx.strokeStyle = "rgba(47,108,246,.96)";
  ctx.lineWidth = Math.max(6, w * .01);
  ctx.beginPath();
  ctx.arc(headX, headY, headRadius, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();

  ctx.shadowBlur = 0;
  ctx.fillStyle = "rgba(47, 108, 246, .9)";
  for (const [x, y] of [leftElbowJoint, leftHand, rightElbowJoint, rightHand, leftKneeJoint, leftFoot, rightKneeJoint, rightFoot]) {
    ctx.beginPath();
    ctx.arc(x, y, Math.max(5, w * .008), 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
  return true;
}

function drawRunningPlayer(ctx, w, h, now) {
  const phase = state.run.lastStepAt ? Math.min(1, (now - state.run.lastStepAt) / 420) : 1;
  const bounce = Math.sin((1 - phase) * Math.PI) * h * .025;
  const arm = clamp(state.run.armSwing || Math.sin(now / 160) * .45, -0.7, 0.7);
  const leg = clamp(state.run.legSwing || Math.sin(now / 150) * .55, -0.8, 0.8);
  const cx = w * .56;
  const hipY = h * .66 - bounce;
  const headY = h * .42 - bounce;
  const bodySegments = [
    [[cx, headY + h * .08], [cx, hipY]],
    [[cx, h * .52 - bounce], [cx - w * (.07 + arm * .035), h * .60 + arm * h * .07 - bounce]],
    [[cx, h * .52 - bounce], [cx + w * (.07 + arm * .035), h * .60 - arm * h * .07 - bounce]],
    [[cx, hipY], [cx - w * (.045 + leg * .045), h * .83 - leg * h * .05]],
    [[cx, hipY], [cx + w * (.045 + leg * .045), h * .83 + leg * h * .05]],
  ];

  ctx.save();
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.shadowColor = "rgba(47,108,246,.8)";
  ctx.shadowBlur = 20;

  ctx.strokeStyle = "rgba(47,108,246,.95)";
  ctx.lineWidth = Math.max(18, w * .028);
  for (const [from, to] of bodySegments) {
    ctx.beginPath();
    ctx.moveTo(from[0], from[1]);
    ctx.lineTo(to[0], to[1]);
    ctx.stroke();
  }

  ctx.strokeStyle = "#f8fbff";
  ctx.lineWidth = Math.max(9, w * .018);
  for (const [from, to] of bodySegments) {
    ctx.beginPath();
    ctx.moveTo(from[0], from[1]);
    ctx.lineTo(to[0], to[1]);
    ctx.stroke();
  }

  const head = ctx.createRadialGradient(cx - w * .018, headY - h * .014, 2, cx, headY, h * .055);
  head.addColorStop(0, "#ffffff");
  head.addColorStop(1, "#dfe8f7");
  ctx.strokeStyle = "rgba(47,108,246,.95)";
  ctx.lineWidth = Math.max(6, w * .01);
  ctx.fillStyle = head;
  ctx.beginPath();
  ctx.arc(cx, headY, h * .055, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();

  ctx.fillStyle = "rgba(47,108,246,.96)";
  for (const [, [x, y]] of bodySegments.slice(1)) {
    ctx.beginPath();
    ctx.arc(x, y, Math.max(6, w * .009), 0, Math.PI * 2);
    ctx.fill();
  }

  ctx.shadowBlur = 0;
  ctx.fillStyle = "rgba(7, 15, 26, .72)";
  roundedRect(ctx, w * .36, h * .08, w * .28, h * .08, 16);
  ctx.fill();
  ctx.fillStyle = "#ffffff";
  ctx.font = `${Math.max(16, w * .018)}px Microsoft YaHei`;
  ctx.textAlign = "center";
  ctx.fillText(`${state.run.status || "Running"} ${Math.round(state.run.cadence || 0)} spm`, w * .5, h * .132);
  ctx.restore();
}

function drawBoxingPlayer(ctx, w, h, now) {
  const flash = state.game.inputFlash;
  const punchBoost = flash && now - flash.time < 220 ? 0.35 : 0;
  const leftPunch = clamp(state.boxing.leftArm + (flash?.action === "left" ? punchBoost : 0), 0, 1);
  const rightPunch = clamp(state.boxing.rightArm + (flash?.action === "right" ? punchBoost : 0), 0, 1);
  const crouch = clamp(state.boxing.crouch + (flash?.action === "duck" && now - flash.time < 260 ? 0.35 : 0), 0, 1);
  const cx = w * .5;
  const baseY = h * (.77 + crouch * .08);
  const shoulderY = h * (.49 + crouch * .08);
  const hipY = h * (.66 + crouch * .08);
  const headY = h * (.36 + crouch * .08);

  ctx.save();
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.shadowColor = "rgba(255,255,255,.46)";
  ctx.shadowBlur = 20;

  const body = ctx.createLinearGradient(cx, headY, cx, baseY);
  body.addColorStop(0, "#ffffff");
  body.addColorStop(1, "#dbe7ff");
  ctx.strokeStyle = body;
  ctx.lineWidth = Math.max(12, w * .02);

  ctx.beginPath();
  ctx.moveTo(cx, headY + h * .07);
  ctx.lineTo(cx, hipY);
  ctx.stroke();

  ctx.strokeStyle = "#f7fbff";
  ctx.beginPath();
  ctx.moveTo(cx, shoulderY);
  ctx.lineTo(cx - w * (.09 + leftPunch * .18), h * (.55 - leftPunch * .10 + crouch * .07));
  ctx.moveTo(cx, shoulderY);
  ctx.lineTo(cx + w * (.09 + rightPunch * .18), h * (.55 - rightPunch * .10 + crouch * .07));
  ctx.stroke();

  ctx.beginPath();
  ctx.moveTo(cx, hipY);
  ctx.lineTo(cx - w * .075, baseY);
  ctx.moveTo(cx, hipY);
  ctx.lineTo(cx + w * .075, baseY);
  ctx.stroke();

  ctx.fillStyle = "#ffffff";
  ctx.beginPath();
  ctx.arc(cx, headY, h * .055, 0, Math.PI * 2);
  ctx.fill();

  ctx.shadowBlur = 0;
  ctx.fillStyle = "rgba(7, 15, 26, .76)";
  roundedRect(ctx, w * .36, h * .08, w * .28, h * .08, 16);
  ctx.fill();
  ctx.fillStyle = "#ffffff";
  ctx.font = `${Math.max(16, w * .018)}px Microsoft YaHei`;
  ctx.textAlign = "center";
  ctx.fillText(state.boxing.status || "Boxing", w * .5, h * .132);
  ctx.restore();
}

function drawParticles(ctx, delta) {
  state.game.particles.forEach((p) => {
    p.life -= delta;
    p.x += p.vx * delta;
    p.y += p.vy * delta;
    ctx.globalAlpha = Math.max(0, p.life);
    ctx.fillStyle = p.color;
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = 1;
  });
  state.game.particles = state.game.particles.filter((p) => p.life > 0);
}

function roundedRect(ctx, x, y, width, height, radius) {
  const r = Math.min(radius, width / 2, height / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + width - r, y);
  ctx.quadraticCurveTo(x + width, y, x + width, y + r);
  ctx.lineTo(x + width, y + height - r);
  ctx.quadraticCurveTo(x + width, y + height, x + width - r, y + height);
  ctx.lineTo(x + r, y + height);
  ctx.quadraticCurveTo(x, y + height, x, y + height - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

function handleAction(action, fromPose = false) {
  const now = performance.now();
  if (fromPose && now - state.lastPoseActionAt < (isRunningMode() ? 160 : 520)) return;
  if (fromPose) state.lastPoseActionAt = now;

  if (state.game.playerLocked || state.game.poseDriven) {
    const labelMap = { left: "左拳", right: "右拳", duck: "下蹲闪避", step: "动作命中" };
    state.game.action = labelMap[action] || "识别中";
    $("currentAction").textContent = state.game.action;
    return;
  }

  if (isRunningMode()) {
    state.game.action = "步频命中";
    state.game.inputFlash = { action: "step", time: now };
    $("currentAction").textContent = state.run.status || "跑步中";
    if (!state.game.running) {
      drawGame();
      return;
    }
    const hitZone = state.game.targets
      .filter((target) => target.z > 0.42)
      .sort((a, b) => b.z - a.z)[0];
    if (hitZone) {
      hitZone.hit = true;
      state.game.combo += 1;
      state.game.bestCombo = Math.max(state.game.bestCombo, state.game.combo);
      state.game.score += 42 + state.game.combo * 6;
      burst(hitZone);
    } else {
      state.game.combo = Math.max(0, state.game.combo - 1);
    }
    state.poseScore = clamp(Math.round(Math.max(state.poseScore, 70) + Math.min(18, state.game.combo * 1.6)), 40, 100);
    $("scoreInput").value = Math.round(state.poseScore);
    return;
  }

  const labelMap = { left: "左挥击", right: "右挥击", duck: "下蹲闪避" };
  state.game.action = labelMap[action] || "识别中";
  state.game.inputFlash = { action, time: now };
  $("currentAction").textContent = state.game.action;

  if (!state.game.running) {
    drawGame();
    return;
  }

  const hitZone = state.game.targets
    .filter((target) => target.type === action && target.z > 0.50)
    .sort((a, b) => b.z - a.z)[0];
  if (!hitZone) {
    state.game.combo = 0;
    return;
  }

  hitZone.hit = true;
  state.game.combo += 1;
  state.game.bestCombo = Math.max(state.game.bestCombo, state.game.combo);
  state.game.score += 50 + state.game.combo * 8;
  state.poseScore = clamp(72 + state.game.combo * 2 + Math.min(18, state.game.score / 180), 40, 100);
  $("scoreInput").value = Math.round(state.poseScore);
  burst(hitZone);
}

function burst(target) {
  const canvas = $("gameCanvas");
  const x = canvas.width * target.x + (target.x - 0.5) * target.z * canvas.width * 0.2;
  const y = canvas.height * target.y;
  for (let i = 0; i < 20; i += 1) {
    state.game.particles.push({
      x,
      y,
      vx: (Math.random() - 0.5) * 430,
      vy: (Math.random() - 0.5) * 360,
      r: 3 + Math.random() * 5,
      life: 0.45 + Math.random() * 0.32,
      color: target.type === "duck" ? "#ffd0cc" : target.type === "energy" ? "#ffe68a" : "#91edff",
    });
  }
}

function updatePoseReadout(actionScore, status, confidence, symmetry) {
  if (state.game.finished) return;
  const score = clamp(Math.round(actionScore), 40, 100);
  state.poseScore = score;
  if (state.game.running && state.game.poseActive) {
    state.poseStats.frames += 1;
    state.poseStats.totalScore += score;
    state.poseStats.bestScore = Math.max(state.poseStats.bestScore, score);
  }
  $("poseConfidence").textContent = `${confidence}%`;
  $("stabilityScore").textContent = Math.round(symmetry);
  $("scoreValue").textContent = score;
  $("scoreInput").value = score;
  $("currentAction").textContent = status;
}

function countRecognizedRep(action, cooldown = 650) {
  if (!state.game.running || state.game.finished) return;
  const now = performance.now();
  if (now - state.poseStats.lastRepAt < cooldown) return;
  state.poseStats.lastRepAt = now;
  state.poseStats.reps += 1;
  state.game.action = action;
  state.game.score += 36 + Math.min(12, state.poseStats.reps) * 4;
  state.game.bestCombo = Math.max(state.game.bestCombo, state.poseStats.reps);
  if (state.poseStats.reps >= state.poseStats.targetReps) {
    finishGame("动作完成");
  }
}

function getFinalPoseScore() {
  const stats = state.poseStats;
  const average = stats.frames ? stats.totalScore / stats.frames : state.poseScore;
  const best = stats.bestScore || state.poseScore;
  const completion = stats.targetReps ? clamp(stats.reps / stats.targetReps, 0, 1) : 0;
  return clamp(Math.round(average * 0.72 + best * 0.18 + completion * 10), 40, 100);
}

function finishGame(reason = "倒计时结束") {
  if (state.game.finished) return;
  state.game.finished = true;
  state.game.running = false;
  state.game.poseActive = false;
  state.game.poseDriven = false;
  if (state.game.loopId) {
    cancelAnimationFrame(state.game.loopId);
    state.game.loopId = null;
  }
  if (state.game.countdownId) {
    clearInterval(state.game.countdownId);
    state.game.countdownId = null;
  }
  const finalScore = getFinalPoseScore();
  state.poseScore = finalScore;
  $("startGameBtn").textContent = "重新开始";
  $("startGameBtn").classList.remove("is-running");
  state.game.action = "已完成";
  $("currentAction").textContent = "已完成";
  $("scoreValue").textContent = finalScore;
  $("scoreInput").value = finalScore;
  stopCameraRecognition({ silent: true });
  $("gameResult").innerHTML = `
    <strong>${reason}：动作评分 ${finalScore}，完成 ${state.poseStats.reps}/${state.poseStats.targetReps}</strong>
    <p>摄像头识别已停止。点击“完成关卡结算”，动作评估智能体会把评分写入报告，图谱推荐智能体会刷新下一轮方案。</p>
  `;
}

function updateHud() {
  $("liveScore").textContent = state.game.score;
  $("comboValue").textContent = state.game.combo;
  $("timeLeft").textContent = Math.ceil(state.game.timeLeft);
  $("scoreValue").textContent = Math.round(state.poseScore);
}

function loadScriptOnce(src) {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${src}"]`);
    if (existing) {
      if (existing.dataset.loaded === "true") {
        resolve();
      } else {
        existing.addEventListener("load", resolve, { once: true });
        existing.addEventListener("error", reject, { once: true });
      }
      return;
    }

    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.onload = () => {
      script.dataset.loaded = "true";
      resolve();
    };
    script.onerror = () => reject(new Error(`MediaPipe Pose script unavailable: ${src}`));
    document.head.appendChild(script);
  });
}

function stopCameraRecognition({ silent = false } = {}) {
  state.cameraRequestId += 1;
  if (state.game.poseLoopId) {
    cancelAnimationFrame(state.game.poseLoopId);
    state.game.poseLoopId = null;
  }
  if (state.game.previewLoopId) {
    cancelAnimationFrame(state.game.previewLoopId);
    state.game.previewLoopId = null;
  }
  state.game.poseActive = false;
  if (state.cameraStream) {
    state.cameraStream.getTracks().forEach((track) => track.stop());
  }
  if (state.cameraVideo) {
    state.cameraVideo.pause?.();
    state.cameraVideo.srcObject = null;
    state.cameraVideo.classList.remove("active");
  }
  setCameraPreviewVisible(false);
  state.cameraStream = null;
  state.cameraVideo = null;
  state.latestLandmarks = null;
  state.lastVideoTime = -1;
  state.poseBusy = false;
  state.lastLandmarkAt = 0;
  if (!silent) setStatus("摄像头识别已停止。", "warn");
}

function waitForVideoReady(video) {
  if (video.readyState >= 2 && video.videoWidth > 0) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      cleanup();
      reject(new Error("摄像头已授权，但没有收到有效视频画面"));
    }, 5000);
    const cleanup = () => {
      window.clearTimeout(timeout);
      video.removeEventListener("loadedmetadata", onReady);
      video.removeEventListener("canplay", onReady);
      video.removeEventListener("error", onError);
    };
    const onReady = () => {
      if (video.videoWidth > 0) {
        cleanup();
        resolve();
      }
    };
    const onError = () => {
      cleanup();
      reject(new Error("摄像头预览播放失败"));
    };
    video.addEventListener("loadedmetadata", onReady);
    video.addEventListener("canplay", onReady);
    video.addEventListener("error", onError);
  });
}

function getCameraPreviewCanvas() {
  const stage = document.querySelector(".virtual-stage");
  if (!stage) return null;
  let canvas = $("cameraPreviewCanvas");
  if (!canvas) {
    canvas = document.createElement("canvas");
    canvas.id = "cameraPreviewCanvas";
    canvas.width = 320;
    canvas.height = 240;
    stage.appendChild(canvas);
  }
  return canvas;
}

function setCameraPreviewVisible(visible) {
  const canvas = $("cameraPreviewCanvas");
  if (!canvas) return;
  canvas.classList.toggle("active", visible);
  $("cameraDeviceSelect")?.classList.toggle("active", visible);
}

function drawCameraPreview(video, landmarks = null) {
  const canvas = getCameraPreviewCanvas();
  if (!canvas || !video || !video.videoWidth) return;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  if (!landmarks?.length) {
    ctx.fillStyle = "rgba(8, 17, 31, .72)";
    ctx.fillRect(0, canvas.height - 30, canvas.width, 30);
    ctx.fillStyle = "#fff";
    ctx.font = "14px Microsoft YaHei";
    ctx.fillText("等待完整人体入镜", 12, canvas.height - 10);
    return;
  }

  ctx.fillStyle = "rgba(47,108,246,.95)";
  for (const index of [0, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28]) {
    const point = landmarks[index];
    if (!point || point.visibility < 0.35) continue;
    const x = canvas.width - point.x * canvas.width;
    const y = point.y * canvas.height;
    ctx.beginPath();
    ctx.arc(x, y, 3.5, 0, Math.PI * 2);
    ctx.fill();
  }
}

function getCameraDeviceSelect() {
  const stage = document.querySelector(".virtual-stage");
  if (!stage) return null;
  let select = $("cameraDeviceSelect");
  if (!select) {
    select = document.createElement("select");
    select.id = "cameraDeviceSelect";
    select.title = "切换摄像头";
    select.addEventListener("change", async () => {
      state.cameraDeviceId = select.value;
      if (state.cameraStream) {
        stopCameraRecognition({ silent: true });
        state.game.poseActive = true;
        await openCamera();
      }
    });
    stage.appendChild(select);
  }
  return select;
}

async function refreshCameraDevices() {
  const select = getCameraDeviceSelect();
  if (!select || !navigator.mediaDevices?.enumerateDevices) return;
  const devices = await navigator.mediaDevices.enumerateDevices();
  const cameras = devices.filter((device) => device.kind === "videoinput");
  select.innerHTML = cameras.length
    ? cameras.map((device, index) => `<option value="${device.deviceId}">${device.label || `摄像头 ${index + 1}`}</option>`).join("")
    : `<option value="">未发现摄像头</option>`;
  if (state.cameraDeviceId && cameras.some((device) => device.deviceId === state.cameraDeviceId)) {
    select.value = state.cameraDeviceId;
  } else if (cameras[0]) {
    state.cameraDeviceId = cameras[0].deviceId;
    select.value = state.cameraDeviceId;
  }
}

function getCameraConstraints() {
  return state.cameraDeviceId
    ? { width: 960, height: 540, deviceId: { exact: state.cameraDeviceId } }
    : { width: 960, height: 540, facingMode: "user" };
}

function loopCameraPreview() {
  const video = state.cameraVideo;
  if (!state.cameraStream || !video) {
    state.game.previewLoopId = null;
    return;
  }
  drawCameraPreview(video, state.latestLandmarks);
  state.game.previewLoopId = requestAnimationFrame(loopCameraPreview);
}

function startCameraPreviewLoop() {
  setCameraPreviewVisible(true);
  if (!state.game.previewLoopId) {
    state.game.previewLoopId = requestAnimationFrame(loopCameraPreview);
  }
}

async function preparePoseModel() {
  if (state.modelReady) return;
  setStatus("正在加载 MediaPipe Pose Landmarker...");
  await loadScriptOnce(`${MEDIAPIPE_POSE_BASE}/pose.js`);
  if (!window.Pose) throw new Error("MediaPipe Pose script loaded but Pose is missing");

  const pose = new window.Pose({
    locateFile: (file) => `${MEDIAPIPE_POSE_BASE}/${file}`,
  });
  pose.setOptions({
    modelComplexity: 1,
    smoothLandmarks: true,
    enableSegmentation: false,
    minDetectionConfidence: 0.55,
    minTrackingConfidence: 0.55,
  });
  pose.onResults((result) => {
    if (result.poseLandmarks?.length) {
      state.latestLandmarks = result.poseLandmarks;
      state.lastPoseAt = performance.now();
      state.lastLandmarkAt = state.lastPoseAt;
      updatePoseMetrics(result.poseLandmarks);
      drawGame();
    } else if (state.game.running && performance.now() - state.lastLandmarkAt > 1800) {
      const video = state.cameraVideo;
      setStatus(`摄像头已开启 ${video?.videoWidth || 0}x${video?.videoHeight || 0}，但暂未检测到完整人体。请后退一些，让头、肩、手、髋、膝、脚踝都进入画面。`, "warn");
      $("currentAction").textContent = "未检测到完整人体";
    }
  });
  await pose.initialize();
  state.poseLandmarker = pose;
  state.modelReady = true;
}

async function openCamera() {
  const rule = getExerciseRule();
  try {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("当前浏览器不支持摄像头访问，请使用最新版 Chrome 或 Edge。");
    }
    const requestId = ++state.cameraRequestId;
    state.game.poseActive = true;
    if (state.cameraStream && state.cameraVideo) {
      startCameraPreviewLoop();
      if (state.modelReady && !state.game.poseLoopId) state.game.poseLoopId = requestAnimationFrame(predictPose);
      setStatus(`${rule.cameraPrompt} 摄像头画面已显示，正在识别人体关键点。`, "ready");
      return;
    }
    const video = $("cameraPreview");
    video.muted = true;
    video.autoplay = true;
    video.playsInline = true;
    video.setAttribute("playsinline", "");
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: getCameraConstraints(),
        audio: false,
      });
    } catch (error) {
      state.cameraDeviceId = "";
      stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 960, height: 540, facingMode: "user" },
        audio: false,
      });
    }
    if (requestId !== state.cameraRequestId) {
      stream.getTracks().forEach((track) => track.stop());
      return;
    }
    state.cameraStream = stream;
    video.srcObject = state.cameraStream;
    state.cameraVideo = video;
    await video.play();
    await waitForVideoReady(video);
    if (!video.videoWidth) throw new Error("摄像头没有输出画面，请检查系统隐私开关或浏览器权限");
    video.classList.add("active");
    drawCameraPreview(video);
    startCameraPreviewLoop();
    await refreshCameraDevices();
    const [track] = stream.getVideoTracks();
    state.cameraDeviceId = track?.getSettings?.().deviceId || state.cameraDeviceId;
    const select = $("cameraDeviceSelect");
    if (select && state.cameraDeviceId) select.value = state.cameraDeviceId;
    setStatus(`摄像头已打开 ${video.videoWidth}x${video.videoHeight}，${track?.label || "摄像头"}。正在加载 MediaPipe...`, "ready");
    $("currentAction").textContent = "摄像头已打开，正在加载识别模型";
  } catch (error) {
    stopCameraRecognition({ silent: true });
    state.game.poseActive = false;
    setStatus("模型或摄像头不可用，已保留键盘演示模式。", "warn");
    toast(`无法启动 MediaPipe：${error.message || "请检查摄像头权限或网络"}`);
    return;
  }

  try {
    await preparePoseModel();
    if (!state.game.poseActive || !state.cameraVideo) return;
    setStatus(`${rule.cameraPrompt} 小人会跟随你的身体关键点实时运动。请让全身进入摄像头画面。`, "ready");
    $("currentAction").textContent = "识别中：请全身入镜";
    if (!state.game.poseLoopId) state.game.poseLoopId = requestAnimationFrame(predictPose);
  } catch (error) {
    state.game.poseActive = false;
    setStatus("摄像头已打开，但 MediaPipe 模型加载失败。请检查网络后重试。", "warn");
    $("currentAction").textContent = "识别模型加载失败";
    toast(`摄像头已打开，但 MediaPipe 加载失败：${error.message || "请检查网络"}`);
  }
}

async function predictPose() {
  if (!state.game.poseActive) {
    state.game.poseLoopId = null;
    return;
  }
  const video = state.cameraVideo;
  if (!state.poseLandmarker || !video || video.readyState < 2) {
    state.game.poseLoopId = requestAnimationFrame(predictPose);
    return;
  }

  if (!state.poseBusy && video.currentTime !== state.lastVideoTime) {
    state.lastVideoTime = video.currentTime;
    state.poseBusy = true;
    try {
      await state.poseLandmarker.send({ image: video });
    } catch (error) {
      console.warn("MediaPipe pose frame failed", error);
    } finally {
      state.poseBusy = false;
    }
  }
  state.game.poseLoopId = state.game.poseActive ? requestAnimationFrame(predictPose) : null;
}

function updatePoseMetrics(landmarks) {
  const visible = landmarks.filter((point) => point.visibility === undefined || point.visibility > 0.55);
  const confidence = Math.round((visible.length / landmarks.length) * 100);
  const shoulder = distance(landmarks[11], landmarks[12]);
  const hip = distance(landmarks[23], landmarks[24]);
  const symmetry = Math.max(0, 100 - Math.abs(shoulder - hip) * 240);

  if (isBoxingMode()) {
    updateBoxingPose(landmarks, confidence, symmetry);
    return;
  }

  if (isRunningMode()) {
    updateRunningPose(landmarks, confidence, symmetry);
    return;
  }

  updateModulePose(landmarks, confidence, symmetry);
}

function updateRunningPose(landmarks, confidence, symmetry) {
  const now = performance.now();
  const leftWrist = landmarks[15];
  const rightWrist = landmarks[16];
  const leftShoulder = landmarks[11];
  const rightShoulder = landmarks[12];
  const leftKnee = landmarks[25];
  const rightKnee = landmarks[26];
  const leftHip = landmarks[23];
  const rightHip = landmarks[24];

  const armSwing = clamp(
    ((rightWrist.y - rightShoulder.y) - (leftWrist.y - leftShoulder.y)) * 2.8,
    -0.8,
    0.8,
  );
  const legSwing = clamp(((rightHip.y - rightKnee.y) - (leftHip.y - leftKnee.y)) * 3.2, -0.8, 0.8);
  const kneeLift = Math.max(leftHip.y - leftKnee.y, rightHip.y - rightKnee.y);
  const side = leftKnee.y < rightKnee.y ? "left" : "right";
  const armSide = armSwing > 0 ? "right" : "left";
  const armMoving = Math.abs(armSwing) > 0.12;
  const kneeMoving = kneeLift > 0.018;

  state.run.armSwing = state.run.armSwing * 0.55 + armSwing * 0.45;
  state.run.legSwing = state.run.legSwing * 0.55 + legSwing * 0.45;

  if (
    (kneeMoving && side !== state.run.lastStepSide || armMoving && armSide !== state.run.lastArmSide) &&
    now - state.run.lastStepAt > 180
  ) {
    if (state.run.lastStepAt) {
      const interval = now - state.run.lastStepAt;
      state.run.cadence = clamp(60000 / interval, 60, 190);
    }
    state.run.lastStepAt = now;
    state.run.lastStepSide = side;
    state.run.lastArmSide = armSide;
    handleAction("step", true);
    countRecognizedRep("步频命中", 260);
  }

  const armScore = clamp(Math.abs(state.run.armSwing) * 130, 35, 100);
  const legScore = clamp(Math.abs(state.run.legSwing) * 145 + kneeLift * 320, 35, 100);
  const cadenceScore = state.run.cadence ? clamp(100 - Math.abs(state.run.cadence - 112) * 0.9, 45, 100) : 55;
  const actionScore = clamp(Math.round(confidence * 0.28 + symmetry * 0.18 + armScore * 0.22 + legScore * 0.2 + cadenceScore * 0.12), 40, 100);

  state.run.status = state.run.cadence >= 125 ? "快跑" : state.run.cadence >= 75 ? "快走" : armMoving ? "摆臂热身" : "准备";
  updatePoseReadout(actionScore, state.run.status, confidence, symmetry);
}

function updateBoxingPose(landmarks, confidence, symmetry) {
  const leftWrist = landmarks[15];
  const rightWrist = landmarks[16];
  const nose = landmarks[0];
  const leftShoulder = landmarks[11];
  const rightShoulder = landmarks[12];
  const hipCenter = { x: (landmarks[23].x + landmarks[24].x) / 2, y: (landmarks[23].y + landmarks[24].y) / 2 };
  const shoulderCenter = { x: (leftShoulder.x + rightShoulder.x) / 2, y: (leftShoulder.y + rightShoulder.y) / 2 };
  const bodyHeight = Math.abs(hipCenter.y - nose.y);

  const leftReach = clamp((leftShoulder.y - leftWrist.y) * 1.5 + (leftShoulder.x - leftWrist.x) * 1.2, 0, 1);
  const rightReach = clamp((rightShoulder.y - rightWrist.y) * 1.5 + (rightWrist.x - rightShoulder.x) * 1.2, 0, 1);
  const crouch = clamp((shoulderCenter.y - 0.42) * 3.4 + (0.36 - bodyHeight) * 2.2, 0, 1);

  state.boxing.leftArm = state.boxing.leftArm * 0.45 + leftReach * 0.55;
  state.boxing.rightArm = state.boxing.rightArm * 0.45 + rightReach * 0.55;
  state.boxing.crouch = state.boxing.crouch * 0.5 + crouch * 0.5;

  if (state.boxing.leftArm > 0.36) {
    state.boxing.status = "左拳";
    handleAction("left", true);
    countRecognizedRep("左拳", 620);
  } else if (state.boxing.rightArm > 0.36) {
    state.boxing.status = "右拳";
    handleAction("right", true);
    countRecognizedRep("右拳", 620);
  } else if (state.boxing.crouch > 0.38) {
    state.boxing.status = "下蹲闪避";
    handleAction("duck", true);
    countRecognizedRep("下蹲闪避", 720);
  } else {
    state.boxing.status = "防守准备";
  }

  const actionScore = clamp(
    Math.round(confidence * 0.3 + symmetry * 0.2 + Math.max(state.boxing.leftArm, state.boxing.rightArm) * 34 + state.boxing.crouch * 16 + 35),
    40,
    100,
  );
  updatePoseReadout(actionScore, state.boxing.status, confidence, symmetry);
}

function updateModulePose(landmarks, confidence, symmetry) {
  const type = getExerciseType();
  const leftWrist = landmarks[15];
  const rightWrist = landmarks[16];
  const leftShoulder = landmarks[11];
  const rightShoulder = landmarks[12];
  const leftHip = landmarks[23];
  const rightHip = landmarks[24];
  const leftKnee = landmarks[25];
  const rightKnee = landmarks[26];
  const leftAnkle = landmarks[27];
  const rightAnkle = landmarks[28];

  const shoulderCenter = midpoint(leftShoulder, rightShoulder);
  const hipCenter = midpoint(leftHip, rightHip);
  const leftKneeAngle = angle(leftHip, leftKnee, leftAnkle);
  const rightKneeAngle = angle(rightHip, rightKnee, rightAnkle);
  const kneeAngle = (leftKneeAngle + rightKneeAngle) / 2;
  const armRaise = clamp(((leftShoulder.y - leftWrist.y) + (rightShoulder.y - rightWrist.y)) * 1.7, 0, 1);
  const armSpread = clamp(Math.abs(leftWrist.x - rightWrist.x) * 1.8, 0, 1);
  const legSpread = clamp(Math.abs(leftAnkle.x - rightAnkle.x) * 2.2, 0, 1);
  const hipDrop = clamp((hipCenter.y - shoulderCenter.y - 0.18) * 2.2, 0, 1);
  const bodyLine = 100 - Math.min(100, Math.abs(leftShoulder.y - leftAnkle.y) * 18 + Math.abs(rightShoulder.y - rightAnkle.y) * 18);
  const torsoTilt = clamp(Math.abs(shoulderCenter.x - hipCenter.x) * 5, 0, 1);

  let status = "\u8bc6\u522b\u4e2d";
  let actionScore = 70;

  if (type === "jumping") {
    const rhythm = clamp((armRaise + legSpread) / 2, 0, 1);
    actionScore = clamp(Math.round(confidence * 0.26 + symmetry * 0.18 + rhythm * 46 + armSpread * 10), 40, 100);
    status = rhythm > 0.58 ? "\u5f00\u5408\u8282\u594f" : "\u51c6\u5907\u5f00\u5408";
    if (rhythm > 0.58) {
      handleAction("step", true);
      countRecognizedRep("开合节奏", 720);
    }
  } else if (type === "stretch") {
    const reach = clamp(Math.max(leftShoulder.y - leftWrist.y, rightShoulder.y - rightWrist.y) * 1.9 + torsoTilt * 0.35, 0, 1);
    actionScore = clamp(Math.round(confidence * 0.3 + symmetry * 0.18 + reach * 42 + armSpread * 10), 40, 100);
    status = reach > 0.5 ? "\u4f38\u5c55\u5230\u4f4d" : "\u7ee7\u7eed\u62c9\u4f38";
    if (reach > 0.5) countRecognizedRep("伸展到位", 900);
  } else if (type === "core") {
    const stability = clamp(bodyLine, 40, 100);
    actionScore = clamp(Math.round(confidence * 0.28 + symmetry * 0.28 + stability * 0.34 + (1 - torsoTilt) * 10), 40, 100);
    status = stability > 76 ? "\u6838\u5fc3\u7a33\u5b9a" : "\u8c03\u6574\u8eab\u4f53\u76f4\u7ebf";
    if (stability > 76) countRecognizedRep("核心稳定", 1000);
  } else if (type === "squat") {
    const squatDepth = clamp((150 - kneeAngle) / 70 + hipDrop * 0.45, 0, 1);
    const kneeControl = clamp(100 - Math.abs(leftKnee.x - leftAnkle.x) * 170 - Math.abs(rightKnee.x - rightAnkle.x) * 170, 40, 100);
    actionScore = clamp(Math.round(confidence * 0.25 + symmetry * 0.17 + squatDepth * 38 + kneeControl * 0.2), 40, 100);
    status = squatDepth > 0.55 ? "\u6df1\u8e72\u5230\u4f4d" : "\u4e0b\u8e72\u51c6\u5907";
    if (squatDepth > 0.55) {
      handleAction("duck", true);
      countRecognizedRep("深蹲到位", 900);
    }
  } else {
    const generalMotion = clamp((armRaise + armSpread + legSpread) / 3, 0, 1);
    actionScore = clamp(Math.round(confidence * 0.32 + symmetry * 0.24 + generalMotion * 44), 40, 100);
    status = generalMotion > 0.45 ? "\u52a8\u4f5c\u8ddf\u968f" : "\u8bc6\u522b\u4e2d";
  }

  updatePoseReadout(actionScore, status, confidence, symmetry);
}

function midpoint(a, b) {
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}

function distance(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function angle(a, b, c) {
  const ab = { x: a.x - b.x, y: a.y - b.y };
  const cb = { x: c.x - b.x, y: c.y - b.y };
  const dot = ab.x * cb.x + ab.y * cb.y;
  const mag = Math.hypot(ab.x, ab.y) * Math.hypot(cb.x, cb.y);
  return Math.acos(clamp(dot / (mag || 1), -1, 1)) * (180 / Math.PI);
}

function normalizeAngle(value) {
  return clamp(100 - Math.abs(value - 110) * 0.9, 45, 100);
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function crowdTone(value) {
  const crowd = Number(value || 0);
  if (crowd >= 70) return "high";
  if (crowd >= 40) return "mid";
  return "low";
}

async function loadAdminData() {
  const equipmentNode = $("equipmentTable");
  if (!equipmentNode || !isAdminUser()) return;
  const adminParams = new URLSearchParams({ admin_user_id: state.user.id });
  if (state.userLocation) {
    adminParams.set("lat", state.userLocation.lat);
    adminParams.set("lon", state.userLocation.lon);
    adminParams.set("location", "浏览器当前位置");
  }
  const adminParam = adminParams.toString();
  try {
    const [mapData, graphData, overviewData, usersData, venuesData, settingsData, exercisesData, rolesData] = await Promise.all([
      api(`/api/admin/equipment-map?${adminParam}`),
      api(`/api/admin/knowledge-graph?${adminParam}`),
      api(`/api/admin/overview?${adminParam}`),
      api(`/api/admin/users?${adminParam}`),
      api(`/api/admin/venues?${adminParam}`),
      api(`/api/admin/settings?${adminParam}`),
      api("/api/exercises"),
      api(`/api/admin/roles?${adminParam}`),
    ]);
    state.admin.equipment = mapData.equipment || [];
    state.admin.venues = mapData.venues || [];
    state.admin.knowledge = graphData || { nodes: [], edges: [] };
    state.admin.overview = overviewData || null;
    state.admin.users = usersData.users || [];
    state.admin.userSegments = usersData.user_segments || [];
    state.admin.venueRows = venuesData.venues || [];
    state.admin.settings = settingsData.settings || [];
    state.admin.exercises = exercisesData.exercises || [];
    state.admin.roles = rolesData.roles || [];
    renderAdminOverview(state.admin.overview);
    renderAdminUserSegments(state.admin.userSegments);
    renderAdminUserTable(state.admin.users);
    renderAdminSettings(state.admin.settings);
    renderNotificationSummary(state.admin.overview?.notifications || []);
    renderAdminCourses(state.admin.exercises);
    renderAdminRoles(state.admin.roles);
    renderAdminManagers(state.admin.users);
    renderAdminDuties();
    renderAdminMetrics(mapData.stats || {});
    renderVenueAdminTable(state.admin.venueRows);
    renderEquipmentTable(state.admin.equipment);
    renderDensityBars(mapData.categories || []);
    renderEquipmentMap(state.admin.venues);
    renderKnowledgeGraph(state.admin.knowledge);
  } catch (error) {
    equipmentNode.textContent = error.message || "管理员数据加载失败";
  }
}

async function refreshAdminData() {
  if (!isAdminUser()) return;
  const location = await updateBrowserLocation();
  if (location) {
    const params = new URLSearchParams({
      admin_user_id: state.user.id,
      lat: location.lat,
      lon: location.lon,
      radius_km: 15,
    });
    try {
      await api(`/api/venues/enrich?${params.toString()}`);
    } catch (error) {
      console.warn("admin venue refresh skipped", error);
    }
  }
  await loadAdminData();
}

function renderAdminOverview(data = {}) {
  renderAdminKpis(data.kpis || []);
  renderAdminTrend(data.training_trend || {});
  renderAdminTrainingTypes(data.training_types || []);
  renderAdminActiveRanking(data.active_ranking || []);
  renderAdminAnnouncements(data.announcements || []);
  renderAdminRecentTraining(data.recent_training || []);
}

function renderAdminKpis(items = []) {
  const node = $("adminOverviewKpis");
  if (!node || !items.length) return;
  const iconMap = {
    users: "👥",
    pulse: "〽",
    dumbbell: "🏋",
    device: "▣",
    flame: "🔥",
  };
  node.innerHTML = items.map((item) => `
    <article>
      <span>${item.label}</span>
      <strong>${item.value}${item.unit ? ` <em>${item.unit}</em>` : ""}</strong>
      <small>${String(item.delta || "").startsWith("+") ? `较昨日 ${item.delta}` : item.delta}</small>
      <i>${iconMap[item.icon] || "●"}</i>
    </article>
  `).join("");
}

function renderAdminTrend(trend = {}) {
  const nodes = nodesById("adminTrainingTrend");
  if (!nodes.length) return;
  const labels = trend.labels || [];
  const newUsers = trend.new_users || [];
  const activeUsers = trend.active_users || [];
  const totalSessions = trend.total_sessions || [];
  if (!labels.length) {
    nodes.forEach((node) => {
      node.innerHTML = `<div class="empty">暂无趋势数据。</div>`;
    });
    return;
  }
  const width = 640;
  const height = 270;
  const maxValue = Math.max(100, ...newUsers, ...activeUsers);
  const xFor = (index) => 44 + index * ((width - 78) / Math.max(labels.length - 1, 1));
  const yFor = (value) => height - 38 - (Number(value || 0) / maxValue) * (height - 80);
  const linePoints = (values) => values.map((value, index) => `${xFor(index)},${yFor(value)}`).join(" ");
  const areaPath = (values) => {
    const points = values.map((value, index) => `${xFor(index)},${yFor(value)}`).join(" L ");
    return `M ${xFor(0)},${height - 38} L ${points} L ${xFor(values.length - 1)},${height - 38} Z`;
  };
  const html = `
    <svg class="trend-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="训练统计趋势图">
      <defs>
        <linearGradient id="adminActiveArea" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stop-color="#2dd4bf" stop-opacity=".38" />
          <stop offset="1" stop-color="#2dd4bf" stop-opacity="0" />
        </linearGradient>
      </defs>
      ${[0, 250, 500, 750, 1000].map((tick) => {
        const y = yFor(tick);
        return `<line x1="44" y1="${y}" x2="${width - 24}" y2="${y}" /><text x="12" y="${y + 4}">${tick.toLocaleString()}</text>`;
      }).join("")}
      ${labels.map((label, index) => `<text class="x-label" x="${xFor(index)}" y="${height - 10}">${label}</text>`).join("")}
      <path class="trend-area" d="${areaPath(activeUsers)}" />
      <polyline class="trend-line trend-new" points="${linePoints(newUsers)}" />
      <polyline class="trend-line trend-active" points="${linePoints(activeUsers)}" />
      ${newUsers.map((value, index) => `<circle class="dot-new" cx="${xFor(index)}" cy="${yFor(value)}" r="4" />`).join("")}
      ${activeUsers.map((value, index) => `<circle class="dot-active" cx="${xFor(index)}" cy="${yFor(value)}" r="4" />`).join("")}
    </svg>
    <div class="trend-legend">
      <span><i class="new"></i>新增用户</span>
      <span><i class="active"></i>活跃用户</span>
      <span><i class="total"></i>总训练次数 ${Number(totalSessions.at(-1) || 0).toLocaleString()}</span>
    </div>
  `;
  nodes.forEach((node) => {
    node.innerHTML = html;
  });
}

function renderAdminTrainingTypes(items = []) {
  const nodes = ["adminTrainingTypes", "adminOverviewTrainingTypes"].map((id) => $(id)).filter(Boolean);
  if (!nodes.length) return;
  const total = items.reduce((sum, item) => sum + Number(item.value || 0), 0);
  if ($("adminTrainingTotalLabel")) {
    $("adminTrainingTotalLabel").textContent = `总训练次数 ${total.toLocaleString()}`;
  }
  if (!items.length) {
    nodes.forEach((node) => {
      node.innerHTML = `<div class="empty">暂无训练类型数据。</div>`;
    });
    return;
  }
  const colors = ["#5b5cff", "#43d6bd", "#8b5cf6", "#ff845d", "#7aa2ff"];
  let start = 0;
  const segments = items.map((item, index) => {
    const end = start + Number(item.percent || 0);
    const segment = `${colors[index % colors.length]} ${start}% ${end}%`;
    start = end;
    return segment;
  }).join(", ");
  const html = `
    <div class="type-donut" style="--segments: ${segments};">
      <strong>${total.toLocaleString()}</strong>
      <span>总训练次数</span>
    </div>
    <div class="type-list">
      ${items.map((item, index) => `
        <p><i style="background:${colors[index % colors.length]}"></i><span>${item.name} ${item.percent}%</span><b>${item.value}</b></p>
      `).join("")}
    </div>
  `;
  nodes.forEach((node) => {
    node.innerHTML = html;
  });
}

function renderAdminUserSegments(items = []) {
  const node = $("adminUserSegments");
  if (!node) return;
  node.innerHTML = items.length ? items.map((item) => {
    const total = Number(item.total || 0);
    const value = Number(item.value || 0);
    const suffix = total ? ` / ${total} 人` : " 人";
    return `
      <p>
        <strong>${item.label}</strong>
        <span>${item.detail || "来自 users 与 sessions 表"}</span>
        <b>${value.toLocaleString()}${suffix}</b>
      </p>
    `;
  }).join("") : `<div class="empty">暂无用户分层数据。</div>`;
}

function renderAdminUserTable(users = []) {
  const node = $("adminUserTable");
  if (!node) return;
  const sorted = [...users].sort((left, right) => {
    if (left.role === right.role) return Number(right.id || 0) - Number(left.id || 0);
    return left.role === "admin" ? -1 : 1;
  });
  node.classList.toggle("empty", !sorted.length);
  node.innerHTML = sorted.length ? `
    <table>
      <thead>
        <tr>
          <th>账号</th><th>昵称</th><th>角色</th><th>等级</th><th>积分</th><th>偏好</th><th>创建时间</th><th>操作</th>
        </tr>
      </thead>
      <tbody>
        ${sorted.map((user) => `
          <tr>
            <td><strong>${user.username}</strong><small>ID ${user.id}</small></td>
            <td>${user.nickname || "-"}</td>
            <td>${user.role === "admin" ? "管理员" : "普通用户"}</td>
            <td>Lv.${user.level || 1}</td>
            <td>${Number(user.points || 0).toLocaleString()}</td>
            <td>${user.preference || "-"}</td>
            <td>${formatTime(user.created_at).slice(0, 10)}</td>
            <td><div class="admin-table-actions">
              <button type="button" data-view-admin-user="${user.id}">查看</button>
              <button type="button" data-quick-reset-user="${user.id}">重置密码</button>
              <button class="danger-btn" type="button" data-quick-delete-user="${user.id}" ${String(user.id) === String(state.user.id) ? "disabled" : ""}>删除</button>
            </div></td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  ` : "暂无用户账号数据。";
  bindAdminUserActionButtons(node, sorted);
}

function bindAdminUserActionButtons(root, users = state.admin.users) {
  root.querySelectorAll("[data-view-admin-user]").forEach((button) => {
    button.addEventListener("click", () => {
      showAdminAccountModal(button.dataset.viewAdminUser).catch((error) => {
        console.error(error);
        toast(error.message || "账号详情加载失败");
      });
    });
  });
  root.querySelectorAll("[data-quick-reset-user]").forEach((button) => {
    button.addEventListener("click", async () => {
      const user = users.find((item) => String(item.id) === String(button.dataset.quickResetUser));
      await showAdminAccountModal(user?.id || button.dataset.quickResetUser);
      const passwordInput = $("adminAccountEditForm")?.querySelector("[name='password']");
      passwordInput?.focus();
    });
  });
  root.querySelectorAll("[data-quick-delete-user]").forEach((button) => {
    button.addEventListener("click", async () => {
      const user = users.find((item) => String(item.id) === String(button.dataset.quickDeleteUser));
      await deleteAdminAccount(user);
    });
  });
}

function renderAdminSettings(items = []) {
  const node = $("adminSettingsList");
  if (!node) return;
  node.innerHTML = items.length ? items.map((item) => `
    <p>
      <strong>${item.label || item.dict_key}</strong>
      <span>${item.description || "后台配置项"}</span>
      <button type="button" class="admin-inline-toggle ${Number(item.enabled) ? "active" : ""}" data-toggle-setting="${item.dict_key}">
        ${Number(item.enabled) ? "开启" : "关闭"}
      </button>
    </p>
  `).join("") : `<div class="empty">暂无运行参数。</div>`;
  node.querySelectorAll("[data-toggle-setting]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.toggleSetting;
      const setting = state.admin.settings.find((item) => item.dict_key === key);
      if (!setting) return;
      setting.enabled = Number(setting.enabled) ? 0 : 1;
      renderAdminSettings(state.admin.settings);
    });
  });
}

function renderNotificationSummary(items = []) {
  const badge = $("notificationBtn")?.querySelector("i");
  if (badge) badge.textContent = String(items.length);
}

function currentNotifications() {
  return isAdminUser()
    ? state.admin.overview?.notifications || []
    : state.dashboard?.notifications || [];
}

function renderAdminActiveRanking(items = []) {
  const nodes = nodesById("adminActiveRanking");
  if (!nodes.length) return;
  const html = items.length ? items.map((item) => `
    <article>
      <b>${item.rank}</b>
      <div>
        <strong>${item.nickname}</strong>
        <span>${item.preference} · ${item.points} 积分</span>
        <i><em style="width:${Math.min(100, Number(item.active_index || 0))}%"></em></i>
      </div>
      <strong>${item.active_index}</strong>
    </article>
  `).join("") : `<div class="empty">暂无活跃用户数据。</div>`;
  nodes.forEach((node) => {
    node.innerHTML = html;
  });
}

function renderAdminAnnouncements(items = []) {
  const nodes = nodesById("adminAnnouncements");
  if (!nodes.length) return;
  const html = items.length ? items.map((item) => `
    <article class="${item.level || "info"}">
      <span>${item.level === "warning" ? "提醒" : item.level === "success" ? "完成" : "通知"}</span>
      <h4>${item.title}</h4>
      <p>${item.content}</p>
      <time>${formatTime(item.published_at).slice(5, 16)}</time>
    </article>
  `).join("") : `<div class="empty">暂无系统公告。</div>`;
  nodes.forEach((node) => {
    node.innerHTML = html;
  });
}

function renderAdminRecentTraining(items = []) {
  const nodes = nodesById("adminRecentTraining");
  if (!nodes.length) return;
  const html = items.length ? `
    <table>
      <thead><tr><th>用户</th><th>训练项目</th><th>训练时长</th><th>消耗卡路里</th><th>完成时间</th></tr></thead>
      <tbody>
        ${items.map((item) => `
          <tr>
            <td>${item.nickname}</td>
            <td>${item.exercise_name}</td>
            <td>${item.duration} 分钟</td>
            <td>${item.points} kcal</td>
            <td>${formatTime(item.created_at)}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  ` : `<div class="empty">暂无近期训练记录。</div>`;
  nodes.forEach((node) => {
    node.innerHTML = html;
  });
}

function renderAdminMetrics(stats) {
  if ($("equipmentTotal")) $("equipmentTotal").textContent = stats.total_count || 0;
  if ($("smartEquipmentTotal")) $("smartEquipmentTotal").textContent = stats.smart_count || 0;
  if ($("averageCrowdIndex")) $("averageCrowdIndex").textContent = stats.average_crowd || 0;
  if ($("dailyUsesTotal")) $("dailyUsesTotal").textContent = stats.daily_uses || 0;
}

function exportAdminReport() {
  if (!isAdminUser()) return;
  const rows = [
    ["名称", "类型", "位置", "智能器材", "状态", "人群密集度", "今日使用次数", "最近维护"],
    ...state.admin.equipment.map((item) => [
      item.name,
      item.category,
      item.location,
      Number(item.is_smart) ? "是" : "否",
      equipmentStatusLabel(item.status),
      item.crowd_index,
      item.daily_uses,
      item.last_maintenance || "",
    ]),
  ];
  const csv = rows.map((row) => row.map((value) => `"${String(value ?? "").replaceAll('"', '""')}"`).join(",")).join("\n");
  const blob = new Blob([`\ufeff${csv}`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `fitflow-equipment-report-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function focusKnowledgeGraph() {
  showView("adminGames");
  setTimeout(() => {
    document.querySelector(".kg-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, 220);
}

function focusAdminSection(button) {
  if (!isAdminUser() || !button?.dataset.adminTarget) return;
  const target = $(button.dataset.adminTarget);
  if (!target) return;
  document.querySelectorAll(".nav.admin-only").forEach((item) => {
    item.classList.toggle("active", item === button);
  });
  setTimeout(() => target.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
}

function renderVenueAdminTable(items = []) {
  const node = $("venueAdminTable");
  if (!node) return;
  node.classList.toggle("empty", !items.length);
  node.innerHTML = items.length ? `
    <table>
      <thead>
        <tr>
          <th>ID</th><th>场馆名称</th><th>类型</th><th>位置</th><th>经纬度</th><th>设施</th><th>容量</th><th>人流</th><th>开放时间</th><th>操作</th>
        </tr>
      </thead>
      <tbody>
        ${items.map((item) => `
          <tr>
            <td>${item.id}</td>
            <td><strong>${item.display_name || item.name}</strong><small>${item.name}</small></td>
            <td>${item.sport_type || item.leisure_type || item.kind || "-"}</td>
            <td>${item.resolved_address || item.location}</td>
            <td>${Number(item.latitude || 0).toFixed(4)}, ${Number(item.longitude || 0).toFixed(4)}</td>
            <td>${item.equipment || "-"}</td>
            <td>${item.capacity || 0}</td>
            <td><b class="crowd ${crowdTone(item.crowd_index)}">${item.crowd_index}</b></td>
            <td>${item.open_hours || "-"}</td>
            <td><div class="admin-table-actions">
              <button type="button" data-edit-venue="${item.id}">编辑</button>
              <button class="danger-btn" type="button" data-delete-venue="${item.id}">删除</button>
            </div></td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  ` : "暂无场馆数据。";
  node.querySelectorAll("[data-edit-venue]").forEach((button) => {
    button.addEventListener("click", () => showVenueFormModal(items.find((item) => String(item.id) === button.dataset.editVenue)));
  });
  node.querySelectorAll("[data-delete-venue]").forEach((button) => {
    button.addEventListener("click", () => deleteVenue(button.dataset.deleteVenue));
  });
}

function renderEquipmentTable(items = []) {
  const nodes = nodesById("equipmentTable");
  if (!nodes.length) return;
  const html = items.length ? `
    <table>
      <thead>
        <tr>
          <th>ID</th><th>器材名称</th><th>类型</th><th>所属场馆</th><th>位置</th><th>经纬度</th><th>智能</th><th>状态</th><th>厂商</th><th>密集度</th><th>今日使用</th><th>最近维护</th><th>操作</th>
        </tr>
      </thead>
      <tbody>
        ${items.map((item) => `
          <tr>
            <td>${item.id}</td>
            <td><strong>${item.name}</strong><small>${item.venue_name || item.manufacturer || ""}</small></td>
            <td>${item.category}</td>
            <td>${item.venue_name || "-"}</td>
            <td>${item.location}</td>
            <td>${Number(item.latitude || 0).toFixed(4)}, ${Number(item.longitude || 0).toFixed(4)}</td>
            <td>${Number(item.is_smart) ? "是" : "否"}</td>
            <td><span class="status-pill ${item.status}">${equipmentStatusLabel(item.status)}</span></td>
            <td>${item.manufacturer || "-"}</td>
            <td><b class="crowd ${crowdTone(item.crowd_index)}">${item.crowd_index}</b></td>
            <td>${item.daily_uses || 0}</td>
            <td>${item.last_maintenance || "-"}</td>
            <td><div class="admin-table-actions">
              <button type="button" data-edit-equipment="${item.id}">编辑</button>
              <button class="danger-btn" type="button" data-delete-equipment="${item.id}">删除</button>
            </div></td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  ` : "暂无器材数据。";
  nodes.forEach((node) => {
    node.classList.toggle("empty", !items.length);
    node.innerHTML = html;
    node.querySelectorAll("[data-edit-equipment]").forEach((button) => {
      button.addEventListener("click", () => showEquipmentFormModal(items.find((item) => String(item.id) === button.dataset.editEquipment)));
    });
    node.querySelectorAll("[data-delete-equipment]").forEach((button) => {
      button.addEventListener("click", () => deleteEquipment(button.dataset.deleteEquipment));
    });
  });
}

function equipmentStatusLabel(value) {
  return value === "maintenance" ? "维护中" : value === "offline" ? "停用" : "正常";
}

function showEquipmentFormModal(item = null) {
  const venues = state.admin.venueRows || [];
  showAdminModal(
    item?.id ? "编辑器材" : "新增器材",
    "保存后同步更新器材台账和地图密度",
    `
      <form id="adminEquipmentEditForm" class="admin-modal-form">
        <input name="id" type="hidden" value="${escapeHtml(item?.id || "")}">
        <label>名称<input name="name" required value="${escapeHtml(item?.name || "智能深蹲架 A1")}"></label>
        <label>类型<input name="category" required value="${escapeHtml(item?.category || "力量训练")}"></label>
        <label>所属场馆
          <select name="venue_id">
            <option value="">未绑定场馆</option>
            ${venues.map((venue) => `<option value="${venue.id}" ${String(item?.venue_id || "") === String(venue.id) ? "selected" : ""}>${escapeHtml(venue.display_name || venue.name)}</option>`).join("")}
          </select>
        </label>
        <label>位置<input name="location" required value="${escapeHtml(item?.location || "河北体育馆力量区")}"></label>
        <label>纬度<input name="latitude" type="number" step="0.000001" required value="${escapeHtml(item?.latitude || "38.0427")}"></label>
        <label>经度<input name="longitude" type="number" step="0.000001" required value="${escapeHtml(item?.longitude || "114.5149")}"></label>
        <label>状态
          <select name="status">
            ${["normal:正常", "maintenance:维护中", "offline:停用"].map((option) => {
              const [value, label] = option.split(":");
              return `<option value="${value}" ${(item?.status || "normal") === value ? "selected" : ""}>${label}</option>`;
            }).join("")}
          </select>
        </label>
        <label>厂商<input name="manufacturer" value="${escapeHtml(item?.manufacturer || "FitFlow Lab")}"></label>
        <label>人群密集度<input name="crowd_index" type="number" min="0" max="100" value="${escapeHtml(item?.crowd_index ?? 68)}"></label>
        <label>今日使用次数<input name="daily_uses" type="number" min="0" value="${escapeHtml(item?.daily_uses ?? 126)}"></label>
        <label>最近维护<input name="last_maintenance" type="date" value="${escapeHtml(item?.last_maintenance ? String(item.last_maintenance).slice(0, 10) : "2026-05-10")}"></label>
        <label class="check-line"><input name="is_smart" type="checkbox" ${Number(item?.is_smart ?? 1) ? "checked" : ""}> 智能器材</label>
        <label class="wide-field">说明<textarea name="description">${escapeHtml(item?.description || "支持姿态识别、次数统计和动作风险提醒。")}</textarea></label>
        <div class="form-actions">
          <button class="primary-btn" type="submit">保存器材</button>
          <button type="button" data-close-admin-modal>取消</button>
        </div>
      </form>
    `,
  );
  $("adminEquipmentEditForm")?.addEventListener("submit", submitEquipmentModal);
  document.querySelector("[data-close-admin-modal]")?.addEventListener("click", closeReportModal);
}

async function submitEquipmentModal(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  const payload = {
    admin_user_id: state.user.id,
    id: data.get("id"),
    name: data.get("name"),
    category: data.get("category"),
    venue_id: data.get("venue_id"),
    location: data.get("location"),
    latitude: data.get("latitude"),
    longitude: data.get("longitude"),
    status: data.get("status"),
    manufacturer: data.get("manufacturer"),
    crowd_index: data.get("crowd_index"),
    daily_uses: data.get("daily_uses"),
    last_maintenance: data.get("last_maintenance"),
    is_smart: data.has("is_smart"),
    description: data.get("description"),
  };
  await api("/api/admin/equipment", { method: "POST", body: JSON.stringify(payload) });
  closeReportModal();
  await loadAdminData();
}

async function deleteEquipment(id) {
  if (!id || !(await confirmAction("确定删除该器材吗？"))) return;
  await api("/api/admin/equipment/delete", { method: "POST", body: JSON.stringify({ id, admin_user_id: state.user.id }) });
  await loadAdminData();
}

function showVenueFormModal(item = null) {
  showAdminModal(
    item?.id ? "编辑场馆" : "新增场馆",
    "保存后同步更新场馆台账、器材绑定下拉框和地图",
    `
      <form id="adminVenueEditForm" class="admin-modal-form">
        <input name="id" type="hidden" value="${escapeHtml(item?.id || "")}">
        <label>场馆名称<input name="name" required value="${escapeHtml(item?.name || "全民健身中心")}"></label>
        <label>展示名称<input name="display_name" value="${escapeHtml(item?.display_name || item?.name || "全民健身中心")}"></label>
        <label>位置<input name="location" required value="${escapeHtml(item?.location || "石家庄市长安区")}"></label>
        <label>详细地址<input name="resolved_address" value="${escapeHtml(item?.resolved_address || item?.location || "石家庄市长安区")}"></label>
        <label>纬度<input name="latitude" type="number" step="0.000001" required value="${escapeHtml(item?.latitude || "38.0470")}"></label>
        <label>经度<input name="longitude" type="number" step="0.000001" required value="${escapeHtml(item?.longitude || "114.5140")}"></label>
        <label>运动类型<input name="sport_type" value="${escapeHtml(item?.sport_type || "fitness")}"></label>
        <label>场馆属性
          <select name="kind">
            ${["indoor:室内", "outdoor:室外", "community:社区", "school:校园"].map((option) => {
              const [value, label] = option.split(":");
              return `<option value="${value}" ${(item?.kind || "indoor") === value ? "selected" : ""}>${label}</option>`;
            }).join("")}
          </select>
        </label>
        <label>容量<input name="capacity" type="number" min="1" value="${escapeHtml(item?.capacity || 80)}"></label>
        <label>人流指数<input name="crowd_index" type="number" min="0" max="100" value="${escapeHtml(item?.crowd_index ?? 35)}"></label>
        <label>空气质量<input name="air_quality" type="number" min="0" max="500" value="${escapeHtml(item?.air_quality ?? 60)}"></label>
        <label>开放时间<input name="open_hours" value="${escapeHtml(item?.open_hours || "06:00-22:00")}"></label>
        <label>评分<input name="rating" type="number" min="0" max="5" step="0.1" value="${escapeHtml(item?.rating || 4.6)}"></label>
        <label>设施数量<input name="facility_count" type="number" min="1" value="${escapeHtml(item?.facility_count || 1)}"></label>
        <label>密度评分<input name="density_score" type="number" min="0" max="100" value="${escapeHtml(item?.density_score ?? item?.crowd_index ?? 35)}"></label>
        <label class="wide-field">设施说明<textarea name="equipment" required>${escapeHtml(item?.equipment || "智能跑步区、力量训练区、体测设备")}</textarea></label>
        <div class="form-actions">
          <button class="primary-btn" type="submit">保存场馆</button>
          <button type="button" data-close-admin-modal>取消</button>
        </div>
      </form>
    `,
  );
  $("adminVenueEditForm")?.addEventListener("submit", submitVenueModal);
  document.querySelector("[data-close-admin-modal]")?.addEventListener("click", closeReportModal);
}

async function submitVenueModal(event) {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  await api("/api/admin/venue", {
    method: "POST",
    body: JSON.stringify({
      admin_user_id: state.user.id,
      id: data.get("id"),
      name: data.get("name"),
      display_name: data.get("display_name"),
      location: data.get("location"),
      resolved_address: data.get("resolved_address"),
      latitude: data.get("latitude"),
      longitude: data.get("longitude"),
      sport_type: data.get("sport_type"),
      kind: data.get("kind"),
      capacity: data.get("capacity"),
      crowd_index: data.get("crowd_index"),
      air_quality: data.get("air_quality"),
      open_hours: data.get("open_hours"),
      rating: data.get("rating"),
      facility_count: data.get("facility_count"),
      density_score: data.get("density_score"),
      equipment: data.get("equipment"),
    }),
  });
  closeReportModal();
  await loadAdminData();
}

async function deleteVenue(id) {
  if (!id || !(await confirmAction("确定删除该场馆吗？关联器材会自动解除绑定。"))) return;
  await api("/api/admin/venue/delete", { method: "POST", body: JSON.stringify({ id, admin_user_id: state.user.id }) });
  await loadAdminData();
}

function renderDensityBars(categories = []) {
  const node = $("densityBars");
  if (!node) return;
  const max = Math.max(1, ...categories.map((item) => Number(item.average_crowd || 0)));
  node.innerHTML = categories.length ? categories.map((item) => `
    <div class="density-row">
      <span>${item.category}</span>
      <i><b style="width:${Math.max(8, Number(item.average_crowd || 0) / max * 100)}%"></b></i>
      <strong>${item.average_crowd}</strong>
    </div>
  `).join("") : `<div class="empty">暂无分类密集度。</div>`;
}

function renderAdminCourses(items = []) {
  const node = $("adminCourseList");
  if (!node) return;
  const courses = items.slice(0, 12);
  node.innerHTML = courses.length ? courses.map((item) => `
    <article class="admin-course-card">
      <div>
        <b>${item.name}</b>
        <span>${item.category} · 难度 ${item.difficulty}</span>
      </div>
      <p>${item.target || "全身协调"}</p>
      <small>器材：${item.equipment || "徒手"}</small>
      <button type="button" data-edit-course="${item.id}">编辑课程</button>
    </article>
  `).join("") : `
    <article class="admin-course-card">
      <b>暂无课程</b>
      <span>点击新增课程写入 exercises 表。</span>
      <button type="button">新增课程</button>
    </article>
  `;
  node.querySelectorAll("button[type='button']").forEach((button) => {
    button.addEventListener("click", () => {
      handleAdminButton(button).catch((error) => {
        console.error(error);
        toast("操作失败，请稍后重试");
      });
    });
  });
}

function parseRoleRow(item) {
  const parts = String(item.dict_value || "").split("|");
  return {
    name: parts[0] || item.dict_key,
    users: parts[1] || "只读",
    training: parts[2] || "只读",
    courses: parts[3] || "只读",
    equipment: parts[4] || "只读",
    reports: parts[5] || "只读",
    system: parts[6] || "只读",
  };
}

function renderAdminRoles(items = []) {
  const node = $("adminRoleTableBody");
  if (!node) return;
  const roles = items.length ? items.map(parseRoleRow) : [
    { name: "超级管理员", users: "读写", training: "读写", courses: "读写", equipment: "读写", reports: "导出", system: "配置" },
    { name: "运营管理员", users: "读写", training: "读写", courses: "读写", equipment: "只读", reports: "导出", system: "只读" },
    { name: "设备管理员", users: "只读", training: "只读", courses: "只读", equipment: "读写", reports: "导出", system: "只读" },
    { name: "审计员", users: "只读", training: "只读", courses: "只读", equipment: "只读", reports: "只读", system: "审计" },
  ];
  node.innerHTML = roles.map((item) => `
    <tr>
      <td><strong>${item.name}</strong></td>
      <td><span class="permission-pill">${item.users}</span></td>
      <td><span class="permission-pill">${item.training}</span></td>
      <td><span class="permission-pill">${item.courses}</span></td>
      <td><span class="permission-pill">${item.equipment}</span></td>
      <td><span class="permission-pill">${item.reports}</span></td>
      <td><span class="permission-pill">${item.system}</span></td>
    </tr>
  `).join("");
}

function renderAdminManagers(users = []) {
  const node = $("adminManagerList");
  if (!node) return;
  const admins = users.filter((user) => user.role === "admin");
  const source = admins.length ? admins : [
    { nickname: "超级管理员", username: "admin", role: "admin", preference: "全模块管理", created_at: new Date().toISOString() },
  ];
  node.innerHTML = source.map((user) => `
    <article class="admin-manager-card">
      <div class="manager-avatar">${String(user.nickname || user.username || "管").slice(0, 1)}</div>
      <div>
        <strong>${user.nickname || user.username}</strong>
        <span>${user.username} · ${user.role === "admin" ? "管理员" : user.role}</span>
        <small>${user.preference || "后台运营管理"} · 创建于 ${formatTime(user.created_at).slice(0, 10)}</small>
      </div>
      <button type="button" data-view-admin-user="${user.id || ""}">查看账号</button>
    </article>
  `).join("");
  node.querySelectorAll("[data-view-admin-user]").forEach((button) => {
    button.addEventListener("click", () => {
      showAdminAccountModal(button.dataset.viewAdminUser).catch((error) => {
        console.error(error);
        toast(error.message || "账号详情加载失败");
      });
    });
  });
}

function renderAdminDuties() {
  const node = $("adminDutyList");
  if (!node) return;
  const duties = [
    ["用户运营", "处理新手引导、异常积分和用户反馈", "李老师"],
    ["设备巡检", "复核维护中器材、地图密度和工单状态", "王老师"],
    ["权限管理", "复查权限变更、角色调整和配置范围", "赵老师"],
  ];
  node.innerHTML = duties.map(([title, detail, owner]) => `
    <p>
      <strong>${title}</strong>
      <span>${detail}</span>
      <b>${owner}</b>
    </p>
  `).join("");
}

function equipmentToMapItems(items = []) {
  return items
    .filter((item) => Number.isFinite(Number(item.latitude)) && Number.isFinite(Number(item.longitude)))
    .map((item) => ({
      ...item,
      display_name: item.venue_name || item.location || item.name,
      name: item.venue_name || item.location || item.name,
      facility_count: 1,
      density_score: Number(item.crowd_index || 0),
      crowd_index: Number(item.crowd_index || 0),
    }));
}

function renderEquipmentMap(items = []) {
  const node = activeNode("equipmentMap");
  if (!node) return;
  const mapItems = state.admin.venues?.length ? state.admin.venues : items;
  const mappable = normalizeVenueItems(mapItems.length ? mapItems : SHIJIAZHUANG_VENUES)
    .filter((item) => Number.isFinite(Number(item.latitude)) && Number.isFinite(Number(item.longitude)));
  const clusters = buildVenueClusters(mappable);
  const mapPanel = node.closest(".admin-map-panel");
  const mapTitle = mapPanel?.querySelector(".venue-map-head h2");
  const mapIntro = mapPanel?.querySelector(".venue-map-head p");
  if (mapTitle) mapTitle.textContent = "用户端同源场馆地图";
  if (mapIntro) mapIntro.textContent = "点位、当前位置和密度颜色与用户端场馆推荐保持一致。";
  if ($("adminVenueTotalCount")) {
    $("adminVenueTotalCount").textContent = mappable.length;
    $("adminVenueTotalCount").nextElementSibling.textContent = "用户端场馆";
  }
  if ($("adminVenueLowCrowdCount")) {
    $("adminVenueLowCrowdCount").textContent = mappable.filter((item) => item.crowd_index <= 35).length;
    $("adminVenueLowCrowdCount").nextElementSibling.textContent = "低人流";
  }
  if ($("adminVenueAverageDensity")) {
    $("adminVenueAverageDensity").textContent = mappable.length
      ? Math.round(mappable.reduce((sum, item) => sum + item.density_score, 0) / mappable.length)
      : 0;
    $("adminVenueAverageDensity").nextElementSibling.textContent = "平均密度";
  }
  const center = mappable[0] ? [Number(mappable[0].latitude), Number(mappable[0].longitude)] : [38.047, 114.514];
  if (state.admin.map && state.admin.map.getContainer?.() !== node) {
    state.admin.markers.forEach((marker) => marker.remove());
    state.admin.markers = [];
    state.admin.map.remove();
    state.admin.map = null;
  }
  if (window.L && !state.admin.map) {
    state.admin.map = window.L.map(node, { zoomControl: true }).setView(center, 12);
    window.L.tileLayer("http://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}", {
      maxZoom: 18,
      subdomains: ["1", "2", "3", "4"],
      attribution: "OpenStreetMap",
    }).addTo(state.admin.map);
  }
  if (!window.L || !state.admin.map) {
    node.innerHTML = clusters.slice(0, 8).map((cluster) => `
      <button class="map-fallback-point ${crowdTone(cluster.avgCrowd)}" type="button">
        ${cluster.count} 台器材<small>密度 ${Math.round(cluster.density)} / 平均人流 ${Math.round(cluster.avgCrowd)}</small>
      </button>
    `).join("");
    return;
  }
  state.admin.markers.forEach((marker) => marker.remove());
  state.admin.markers = [];
  const userLatLng = state.userLocation
    ? [Number(state.userLocation.lat), Number(state.userLocation.lon)]
    : null;
  if (userLatLng && Number.isFinite(userLatLng[0]) && Number.isFinite(userLatLng[1])) {
    const userMarker = window.L.marker(userLatLng, {
      zIndexOffset: 1000,
      icon: window.L.divIcon({
        className: "user-location-marker",
        html: `<span></span><b>我在这里</b>`,
        iconSize: [96, 40],
        iconAnchor: [18, 34],
      }),
    }).addTo(state.admin.map);
    userMarker.bindPopup(`当前位置<br>精度约 ${state.userLocation.accuracy || "--"} 米`);
    state.admin.markers.push(userMarker);
  }
  clusters.forEach((cluster) => {
    const tone = crowdTone(cluster.avgCrowd);
    const color = tone === "high" ? "#ef4444" : tone === "mid" ? "#f59e0b" : "#22c55e";
    const marker = window.L.circleMarker([cluster.lat, cluster.lon], {
      radius: Math.min(30, 8 + cluster.count * 1.8 + cluster.density / 12),
      color,
      fillColor: color,
      fillOpacity: 0.34,
      weight: 2,
    }).addTo(state.admin.map);
    marker.bindPopup(`
      <strong>该区域 ${cluster.count} 台器材</strong><br>
      场馆密度：${Math.round(cluster.density)}<br>
      平均人流：${Math.round(cluster.avgCrowd)}<br>
      ${cluster.sample.map((item) => `${item.display_name}<br><small>${item.category || "器材"} · ${item.location || ""}</small>`).join("<br>")}
    `);
    marker.bindPopup([
      `<strong>该区域 ${cluster.count} 个场馆</strong>`,
      `场馆密度：${Math.round(cluster.density)}`,
      `平均人流：${Math.round(cluster.avgCrowd)}`,
      ...cluster.sample.map((item) => item.display_name || item.name),
    ].join("<br>"));
    marker.bindPopup([
      `<strong>该区域 ${cluster.count} 个场馆</strong>`,
      `场馆密度：${Math.round(cluster.density)}`,
      `平均人流：${Math.round(cluster.avgCrowd)}`,
      ...cluster.sample.map((item) => item.display_name || item.name),
    ].join("<br>"));
    state.admin.markers.push(marker);
  });
  if (userLatLng && Number.isFinite(userLatLng[0]) && Number.isFinite(userLatLng[1])) {
    state.admin.map.setView(userLatLng, 14);
  } else if (clusters.length) {
    const bounds = window.L.latLngBounds(clusters.map((cluster) => [cluster.lat, cluster.lon]));
    state.admin.map.fitBounds(bounds.pad(0.18), { maxZoom: 13 });
  }
  setTimeout(() => state.admin.map?.invalidateSize(), 80);
}

function renderKnowledgeGraph(graph = { nodes: [], edges: [] }) {
  const graphNodes = nodesById("kgGraph");
  const listNodes = nodesById("kgEdgeList");
  if (!graphNodes.length || !listNodes.length) return;
  const nodes = graph.nodes || [];
  const edges = graph.edges || [];
  let graphHtml = "";
  if (!nodes.length) {
    graphHtml = `<div class="empty">暂无知识图谱节点，保存关系后会自动生成节点。</div>`;
  } else {
    const lanes = [
      { key: "people", label: "人群", x: 13, types: ["group", "population", "user"] },
      { key: "motion", label: "动作 / 部位", x: 38, types: ["exercise", "body_part"] },
      { key: "equipment", label: "器材", x: 63, types: ["equipment"] },
      { key: "ops", label: "场馆 / 运维", x: 87, types: ["venue", "maintenance", "other"] },
    ];
    const laneByType = new Map(lanes.flatMap((lane) => lane.types.map((type) => [type, lane])));
    const buckets = Object.fromEntries(lanes.map((lane) => [lane.key, []]));
    nodes.forEach((node) => {
      const lane = laneByType.get(node.type) || lanes[3];
      buckets[lane.key].push(node);
    });
    const visibleNodes = lanes.flatMap((lane) => {
      const laneNodes = buckets[lane.key].slice(0, 6);
      const step = laneNodes.length > 1 ? 68 / (laneNodes.length - 1) : 0;
      return laneNodes.map((node, index) => ({
        ...node,
        x: lane.x,
        y: laneNodes.length === 1 ? 52 : 18 + index * step,
      }));
    }).slice(0, 18);
    const positionById = new Map(visibleNodes.map((node) => [node.id, node]));
    const positionByName = new Map(visibleNodes.map((node) => [node.name, node]));
    const lines = edges.slice(0, 28).map((edge) => {
      const source = positionById.get(edge.source_key) || positionByName.get(edge.source_name);
      const target = positionById.get(edge.target_key) || positionByName.get(edge.target_name);
      if (!source || !target) return "";
      const controlOffset = Math.max(8, Math.abs(target.x - source.x) * 0.42);
      const c1x = source.x + (target.x >= source.x ? controlOffset : -controlOffset);
      const c2x = target.x - (target.x >= source.x ? controlOffset : -controlOffset);
      const path = `M ${source.x} ${source.y} C ${c1x} ${source.y}, ${c2x} ${target.y}, ${target.x} ${target.y}`;
      return `<path d="${path}" data-weight="${edge.weight || 1}"></path>`;
    }).join("");
    graphHtml = `
      <div class="kg-lane-labels">
        ${lanes.map((lane) => `<span style="--x:${lane.x}%">${lane.label}</span>`).join("")}
      </div>
      <svg class="kg-links" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">${lines}</svg>
      ${visibleNodes.map((node) => `
    <span class="kg-node type-${node.type}" style="--x:${node.x}%;--y:${node.y}%">
      <b>${node.name}</b><small>${node.type}</small>
    </span>
  `).join("")}
    `;
  }
  const listHtml = edges.length ? edges.map((edge) => `
    <div class="kg-edge">
      <strong>${edge.source_name}</strong>
      <em>${edge.relation_type}</em>
      <strong>${edge.target_name}</strong>
      <small>权重 ${edge.weight} · ${edge.note || "无说明"}</small>
      <span>
        ${edge.generated ? `<i>算法生成</i>` : `
          <button type="button" data-edit-kg="${edge.id}">编辑</button>
          <button type="button" data-delete-kg="${edge.id}">删除</button>
        `}
      </span>
    </div>
  `).join("") : "暂无知识图谱关系。";
  graphNodes.forEach((graphNode) => {
    graphNode.innerHTML = graphHtml;
  });
  listNodes.forEach((listNode) => {
    listNode.classList.toggle("empty", !edges.length);
    listNode.innerHTML = listHtml;
    listNode.querySelectorAll("[data-edit-kg]").forEach((button) => {
      button.addEventListener("click", () => showKgFormModal(edges.find((edge) => String(edge.id) === button.dataset.editKg)));
    });
    listNode.querySelectorAll("[data-delete-kg]").forEach((button) => {
      button.addEventListener("click", () => deleteKnowledgeEdge(button.dataset.deleteKg));
    });
  });
}

function showKgFormModal(edge = null) {
  showAdminModal(
    edge?.id ? "编辑体感关卡" : "新建体感关卡",
    "维护器材、动作、场馆和人群的知识图谱关系",
    `
      <form id="adminKgEditForm" class="admin-modal-form">
        <input name="id" type="hidden" value="${escapeHtml(edge?.id || "")}">
        <label>源类型<input name="source_type" required value="${escapeHtml(edge?.source_type || "equipment")}"></label>
        <label>源名称<input name="source_name" required value="${escapeHtml(edge?.source_name || "智能深蹲架 A1")}"></label>
        <label>关系<input name="relation_type" required value="${escapeHtml(edge?.relation_type || "supports")}"></label>
        <label>目标类型<input name="target_type" required value="${escapeHtml(edge?.target_type || "exercise")}"></label>
        <label>目标名称<input name="target_name" required value="${escapeHtml(edge?.target_name || "深蹲")}"></label>
        <label>权重<input name="weight" type="number" min="0" max="1" step="0.01" value="${escapeHtml(edge?.weight ?? 0.95)}"></label>
        <label class="wide-field">关系说明<textarea name="note">${escapeHtml(edge?.note || "")}</textarea></label>
        <div class="form-actions">
          <button class="primary-btn" type="submit">保存关卡</button>
          <button type="button" data-close-admin-modal>取消</button>
        </div>
      </form>
    `,
  );
  $("adminKgEditForm")?.addEventListener("submit", submitKnowledgeEdge);
  document.querySelector("[data-close-admin-modal]")?.addEventListener("click", closeReportModal);
}

async function submitKnowledgeEdge(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  const payload = {
    admin_user_id: state.user.id,
    id: data.get("id"),
    source_type: data.get("source_type"),
    source_name: data.get("source_name"),
    relation_type: data.get("relation_type"),
    target_type: data.get("target_type"),
    target_name: data.get("target_name"),
    weight: data.get("weight"),
    note: data.get("note"),
  };
  await api("/api/admin/knowledge-graph", { method: "POST", body: JSON.stringify(payload) });
  closeReportModal();
  await loadAdminData();
}

async function deleteKnowledgeEdge(id) {
  if (!id || !(await confirmAction("确定删除该知识图谱关系吗？"))) return;
  await api("/api/admin/knowledge-graph/delete", { method: "POST", body: JSON.stringify({ id, admin_user_id: state.user.id }) });
  await loadAdminData();
}

function showAdminModal(title, meta, bodyHtml) {
  $("reportModalTitle").textContent = title;
  $("reportModalMeta").textContent = meta || "管理员后台";
  $("reportModalBody").innerHTML = bodyHtml;
  showReportModal();
}

function adminTable(headers, rows) {
  return `
    <div class="admin-modal-table">
      <table>
        <thead><tr>${headers.map((item) => `<th>${item}</th>`).join("")}</tr></thead>
        <tbody>
          ${rows.length ? rows.map((row) => `<tr>${row.map((cell) => `<td>${cell ?? ""}</td>`).join("")}</tr>`).join("") : `<tr><td colspan="${headers.length}">暂无数据</td></tr>`}
        </tbody>
      </table>
    </div>
  `;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

async function showAdminAccountModal(userId) {
  if (!userId) {
    toast("缺少账号 ID，无法查看详情");
    return;
  }
  const params = new URLSearchParams({ admin_user_id: state.user.id, id: userId });
  const data = await api(`/api/admin/user?${params.toString()}`);
  const user = data.user || {};
  const stats = data.stats || {};
  const isSelf = String(user.id) === String(state.user.id);
  showAdminModal(
    `${user.nickname || user.username} 的账号`,
    `账号 ${user.username} · ${user.role === "admin" ? "管理员" : "普通用户"} · 创建于 ${formatTime(user.created_at)}`,
    `
      <div class="modal-grid admin-account-summary">
        <div><strong>积分等级</strong><span>Lv.${user.level || 1} / ${user.points || 0} 积分</span></div>
        <div><strong>训练次数</strong><span>${stats.session_count || 0} 次</span></div>
        <div><strong>平均得分</strong><span>${stats.average_score || 0}</span></div>
        <div><strong>最近训练</strong><span>${stats.last_train_at ? formatTime(stats.last_train_at) : "暂无记录"}</span></div>
      </div>
      <form id="adminAccountEditForm" class="admin-modal-form">
        <input name="id" type="hidden" value="${escapeHtml(user.id)}">
        <label>账号<input name="username" required value="${escapeHtml(user.username)}"></label>
        <label>昵称<input name="nickname" required value="${escapeHtml(user.nickname)}"></label>
        <label>角色
          <select name="role">
            <option value="user" ${user.role !== "admin" ? "selected" : ""}>普通用户</option>
            <option value="admin" ${user.role === "admin" ? "selected" : ""}>管理员</option>
          </select>
        </label>
        <label>新密码<input name="password" type="text" placeholder="留空则不修改密码"></label>
        <label>年龄<input name="age" type="number" min="1" value="${escapeHtml(user.age || 20)}"></label>
        <label>体能水平
          <select name="fitness_level">
            ${["beginner", "intermediate", "advanced"].map((level) => `<option value="${level}" ${user.fitness_level === level ? "selected" : ""}>${level}</option>`).join("")}
          </select>
        </label>
        <label>训练偏好<input name="preference" value="${escapeHtml(user.preference || "")}"></label>
        <label>位置<input name="location" value="${escapeHtml(user.location || "")}"></label>
        <div class="form-actions">
          <button class="primary-btn" type="submit">保存资料</button>
          <button type="button" data-reset-admin-password>重置为上方新密码</button>
          <button class="danger-btn" type="button" data-delete-admin-user ${isSelf ? "disabled" : ""}>删除账号</button>
          <button type="button" data-close-admin-modal>关闭</button>
        </div>
      </form>
    `,
  );
  const formNode = $("adminAccountEditForm");
  formNode?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const saved = await saveAdminAccountForm(form);
    if (String(saved?.id) === String(state.user.id)) {
      setUser({ ...state.user, ...saved });
    }
    await loadAdminData();
    await showAdminAccountModal(saved?.id || user.id);
  });
  document.querySelector("[data-reset-admin-password]")?.addEventListener("click", async () => {
    const form = new FormData(formNode);
    const password = String(form.get("password") || "").trim();
    if (!password) {
      toast("请先在“新密码”里填写要重置成的密码");
      formNode.querySelector("[name='password']")?.focus();
      return;
    }
    form.set("password", password);
    const saved = await saveAdminAccountForm(form);
    await loadAdminData();
    toast(`密码已重置为 ${password}`);
    await showAdminAccountModal(saved?.id || user.id);
  });
  document.querySelector("[data-delete-admin-user]")?.addEventListener("click", async () => {
    await deleteAdminAccount(user);
  });
  document.querySelector("[data-close-admin-modal]")?.addEventListener("click", closeReportModal);
}

async function saveAdminAccountForm(form) {
  const response = await api("/api/admin/user", {
    method: "POST",
    body: JSON.stringify({
      admin_user_id: state.user.id,
      id: form.get("id"),
      role: form.get("role"),
      username: form.get("username"),
      nickname: form.get("nickname"),
      password: form.get("password"),
      age: form.get("age"),
      fitness_level: form.get("fitness_level"),
      preference: form.get("preference"),
      location: form.get("location"),
    }),
  });
  return response.user;
}

async function deleteAdminAccount(user) {
  if (!user?.id) return;
  if (!(await confirmAction(`确定删除账号 ${user.username} 吗？相关训练记录会按数据库外键同步清理。`))) return;
  await api("/api/admin/user/delete", {
    method: "POST",
    body: JSON.stringify({ admin_user_id: state.user.id, id: user.id }),
  });
  await loadAdminData();
  closeReportModal();
  showUsersModal(user.role === "admin" ? "admin" : "");
}

async function recordAdminAction(action, detail = "") {
  if (!isAdminUser()) return;
  try {
    await api("/api/admin/logs", {
      method: "POST",
      body: JSON.stringify({ admin_user_id: state.user.id, action, detail }),
    });
    await loadAdminData();
  } catch (error) {
    console.warn("admin log skipped", error);
  }
}

function showUsersModal(filterRole = "") {
  const users = filterRole ? state.admin.users.filter((user) => user.role === filterRole) : state.admin.users;
  showAdminModal(
    filterRole === "admin" ? "管理员账号" : "用户名单",
    `共 ${users.length} 条记录，数据来自 users 表`,
    adminTable(
      ["账号", "昵称", "角色", "等级", "积分", "偏好", "创建时间", "操作"],
      users.map((user) => [
        user.username,
        user.nickname,
        user.role === "admin" ? "管理员" : "普通用户",
        `Lv.${user.level || 1}`,
        user.points,
        user.preference,
        formatTime(user.created_at),
        `<button type="button" data-view-admin-user="${user.id}">查看</button>
         <button type="button" data-quick-reset-user="${user.id}">重置密码</button>
         <button class="danger-btn" type="button" data-quick-delete-user="${user.id}" ${String(user.id) === String(state.user.id) ? "disabled" : ""}>删除</button>`
      ]),
    ),
  );
  bindAdminUserActionButtons($("reportModalBody"), users);
}

function showEquipmentModal(status = "") {
  const rows = status ? state.admin.equipment.filter((item) => item.status === status) : state.admin.equipment;
  showAdminModal(
    status === "maintenance" ? "维护工单" : "器材台账",
    `共 ${rows.length} 条记录，数据来自 fitness_equipment 表`,
    adminTable(
      ["名称", "类型", "位置", "状态", "密集度", "今日使用", "最近维护"],
      rows.map((item) => [item.name, item.category, item.location, equipmentStatusLabel(item.status), item.crowd_index, item.daily_uses, item.last_maintenance || "-"]),
    ),
  );
}

function showAdminUserForm(role = "user") {
  const isAdmin = role === "admin";
  showAdminModal(
    isAdmin ? "新增管理员" : "新增用户",
    "提交后写入 users 表并刷新后台数据",
    `
      <form id="adminUserCreateForm" class="admin-modal-form">
        <label>账号<input name="username" required placeholder="${isAdmin ? "admin_ops" : "user_001"}"></label>
        <label>昵称<input name="nickname" required placeholder="${isAdmin ? "运营老师" : "新用户"}"></label>
        <label>密码<input name="password" value="${isAdmin ? "admin123" : "123456"}"></label>
        <label>年龄<input name="age" type="number" min="1" value="${isAdmin ? "30" : "20"}"></label>
        <label>体能水平
          <select name="fitness_level">
            <option value="beginner">beginner</option>
            <option value="intermediate">intermediate</option>
            <option value="advanced" ${isAdmin ? "selected" : ""}>advanced</option>
          </select>
        </label>
        <label>训练偏好<input name="preference" value="${isAdmin ? "后台管理" : "综合训练"}"></label>
        <label>位置<input name="location" value="${isAdmin ? "管理中心" : "石家庄市"}"></label>
        <div class="form-actions">
          <button class="primary-btn" type="submit">${isAdmin ? "保存管理员" : "保存用户"}</button>
          <button type="button" data-close-admin-modal>取消</button>
        </div>
      </form>
    `,
  );
  $("adminUserCreateForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await api("/api/admin/user", {
      method: "POST",
      body: JSON.stringify({
        admin_user_id: state.user.id,
        role,
        username: form.get("username"),
        nickname: form.get("nickname"),
        password: form.get("password"),
        age: form.get("age"),
        fitness_level: form.get("fitness_level"),
        preference: form.get("preference"),
        location: form.get("location"),
      }),
    });
    await loadAdminData();
    closeReportModal();
    showUsersModal(isAdmin ? "admin" : "");
  });
  document.querySelector("[data-close-admin-modal]")?.addEventListener("click", closeReportModal);
}

function showAdminCourseForm(course = null) {
  const duration = course?.standard?.duration || "20分钟";
  showAdminModal(
    course ? "编辑课程" : "新增课程",
    "提交后写入 exercises 表并同步课程列表",
    `
      <form id="adminCourseForm" class="admin-modal-form">
        <label>课程名称<input name="name" required value="${course?.name || ""}" placeholder="核心稳定课"></label>
        <label>分类<input name="category" required value="${course?.category || "综合训练"}"></label>
        <label>难度
          <select name="difficulty">
            ${[1, 2, 3, 4, 5].map((level) => `<option value="${level}" ${Number(course?.difficulty || 2) === level ? "selected" : ""}>${level}</option>`).join("")}
          </select>
        </label>
        <label>训练目标<input name="target" required value="${course?.target || "全身协调"}"></label>
        <label>器材<input name="equipment" required value="${course?.equipment || "徒手"}"></label>
        <label>建议时长<input name="duration" value="${duration}"></label>
        <div class="form-actions">
          <button class="primary-btn" type="submit">保存课程</button>
          <button type="button" data-close-admin-modal>取消</button>
        </div>
      </form>
    `,
  );
  $("adminCourseForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await api("/api/admin/exercise", {
      method: "POST",
      body: JSON.stringify({
        admin_user_id: state.user.id,
        id: course?.id || null,
        name: form.get("name"),
        category: form.get("category"),
        difficulty: form.get("difficulty"),
        target: form.get("target"),
        equipment: form.get("equipment"),
        duration: form.get("duration"),
      }),
    });
    await loadAdminData();
    closeReportModal();
  });
  document.querySelector("[data-close-admin-modal]")?.addEventListener("click", closeReportModal);
}

function showAdminRoleForm() {
  showAdminModal(
    "新增角色",
    "提交后写入 dictionaries 表，权限矩阵立即刷新",
    `
      <form id="adminRoleForm" class="admin-modal-form">
        <label>角色名称<input name="name" required placeholder="内容管理员"></label>
        <label>角色标识<input name="key" placeholder="content_admin"></label>
        ${["users:用户", "training:训练", "courses:课程场馆", "equipment:器材", "reports:报表", "system:系统"].map((item) => {
          const [key, label] = item.split(":");
          return `
            <label>${label}
              <select name="${key}">
                <option value="只读">只读</option>
                <option value="读写">读写</option>
                <option value="导出">导出</option>
                <option value="配置">配置</option>
                <option value="审计">审计</option>
              </select>
            </label>
          `;
        }).join("")}
        <div class="form-actions">
          <button class="primary-btn" type="submit">保存角色</button>
          <button type="button" data-close-admin-modal>取消</button>
        </div>
      </form>
    `,
  );
  $("adminRoleForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await api("/api/admin/role", {
      method: "POST",
      body: JSON.stringify({
        admin_user_id: state.user.id,
        name: form.get("name"),
        key: form.get("key"),
        permissions: {
          users: form.get("users"),
          training: form.get("training"),
          courses: form.get("courses"),
          equipment: form.get("equipment"),
          reports: form.get("reports"),
          system: form.get("system"),
        },
      }),
    });
    await loadAdminData();
    closeReportModal();
  });
  document.querySelector("[data-close-admin-modal]")?.addEventListener("click", closeReportModal);
}

async function createAnnouncement() {
  const title = prompt("公告标题", "新的运营通知");
  if (!title) return;
  const content = prompt("公告内容", "请管理员关注今日运营数据变化。");
  if (!content) return;
  await api("/api/admin/announcement", {
    method: "POST",
    body: JSON.stringify({ admin_user_id: state.user.id, title, content, level: "info" }),
  });
  await loadAdminData();
  showAdminModal("公告已发布", "已写入 system_announcements 表", `<p class="modal-summary">${title}</p>`);
}

async function saveAdminSettings() {
  const settings = Object.fromEntries(
    state.admin.settings.map((item) => [item.dict_key, Boolean(Number(item.enabled))]),
  );
  await api("/api/admin/settings", {
    method: "POST",
    body: JSON.stringify({
      admin_user_id: state.user.id,
      settings,
    }),
  });
  await loadAdminData();
  showAdminModal("系统设置已保存", "已写入 dictionaries 表", adminTable(["设置项", "状态"], state.admin.settings.map((item) => [item.label || item.dict_key, Number(item.enabled) ? "开启" : "关闭"])));
}

async function handleAdminButton(button) {
  if (!isAdminUser()) return;
  if (button.id || button.dataset.editKg || button.dataset.deleteKg || button.dataset.editEquipment || button.dataset.deleteEquipment) return;
  if (button.dataset.editCourse) {
    const course = state.admin.exercises.find((item) => String(item.id) === String(button.dataset.editCourse));
    showAdminCourseForm(course);
    return;
  }
  const label = button.textContent.trim().replace(/\s+/g, "");
  const cardTitle = button.closest("article")?.querySelector("b,h3")?.textContent?.trim() || "";
  const actions = {
    新增用户: () => showAdminUserForm("user"),
    新增管理员: () => showAdminUserForm("admin"),
    新增课程: () => showAdminCourseForm(),
    编辑课程: () => showAdminCourseForm(state.admin.exercises.find((item) => item.name === cardTitle) || { name: cardTitle, category: "综合训练", difficulty: 2, target: "全身协调", equipment: "徒手" }),
    新增器材: () => showEquipmentFormModal(),
    新增场馆: () => showVenueFormModal(),
    新增角色: () => showAdminRoleForm(),
    新建公告: createAnnouncement,
    发布公告: createAnnouncement,
    保存配置: saveAdminSettings,
    搜索用户: () => showUsersModal(),
    筛选活跃: () => showUsersModal(),
    查看更多: () => showUsersModal(),
    查看趋势: () => showAdminModal("训练趋势", "数据来自后台概览接口", adminTable(["日期", "新增用户", "活跃用户"], (state.admin.overview?.training_trend?.labels || []).map((label, index) => [label, state.admin.overview.training_trend.new_users[index], state.admin.overview.training_trend.active_users[index]]))),
    异常提醒: () => showEquipmentModal("maintenance"),
    维护工单: () => showEquipmentModal("maintenance"),
    值班安排: () => showAdminModal("值班安排", "管理员值班任务", adminTable(["任务", "职责", "负责人"], [["用户运营", "处理新手引导和异常积分反馈", "李老师"], ["设备巡检", "复核维护中器材和地图密度", "王老师"], ["权限管理", "复查权限变更和角色配置范围", "赵老师"]])),
  };
  const action = actions[label];
  if (action) {
    await action();
    if (!["发布公告", "保存配置", "新增用户", "新增管理员", "新增课程", "编辑课程", "新增器材", "新增场馆", "新增角色"].includes(label)) {
      await recordAdminAction(label, cardTitle || "管理员按钮操作");
    }
  }
}

function bindEvents() {
  document.querySelectorAll(".nav").forEach((button) => {
    button.addEventListener("click", () => {
      showView(button.dataset.view);
      focusAdminSection(button);
    });
  });
  document.querySelectorAll(".admin-view button[type='button']").forEach((button) => {
    button.addEventListener("click", () => {
      handleAdminButton(button).catch((error) => {
        console.error(error);
        toast("操作失败，请稍后重试");
      });
    });
  });
  document.querySelectorAll(".game-card").forEach((card) => {
    card.addEventListener("click", () => chooseExercise(card.dataset.exercise));
  });

  $("railLoginBtn").addEventListener("click", () => {
    if (state.user) {
      logout();
      return;
    }
    showView("profile");
  });
  $("notificationBtn")?.addEventListener("click", async () => {
    if (!isAdminUser() && state.user) {
      await loadDashboard();
    }
    const notifications = currentNotifications();
    $("reportModalTitle").textContent = "消息通知";
    $("reportModalMeta").textContent = isAdminUser() ? "来自后台实时数据" : "来自系统公告与智能体提醒";
    $("reportModalBody").innerHTML = notifications.length ? `
      <div class="modal-grid">
        ${notifications.map((item) => `
          <div><strong>${html(item.title)}</strong><span>${html(item.content || "暂无详细内容")}</span></div>
        `).join("")}
      </div>
    ` : `<p class="modal-summary">暂无新的通知。</p>`;
    showReportModal();
  });
  $("topUserChip")?.addEventListener("click", () => showView("profile"));
  $("topCameraBtn")?.addEventListener("click", () => {
    if (isAdminUser()) return showView("admin");
    showView("game");
    enterTraining($("exerciseSelect")?.value || "拳击挥击");
    openCamera();
  });
  $("connectionBtn")?.addEventListener("click", () => {
    if (isAdminUser()) return showView("admin");
    showView("game");
    enterTraining($("exerciseSelect")?.value || "拳击挥击");
    openCamera();
  });
  $("browseGamesBtn")?.addEventListener("click", () => {
    document.getElementById("gameLobby")?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  $("heroStartBtn").addEventListener("click", () => {
    if (isAdminUser()) return showView("admin");
    chooseExercise("拳击挥击");
  });
  $("loginBtn").addEventListener("click", login);
  $("registerBtn").addEventListener("click", register);
  $("profileLogoutBtn")?.addEventListener("click", logout);
  $("venueSortBtn")?.addEventListener("click", cycleVenueSort);
  $("venueFilterBtn")?.addEventListener("click", cycleVenueFilter);
  $("refreshAdminBtn")?.addEventListener("click", refreshAdminData);
  $("exportAdminReportBtn")?.addEventListener("click", exportAdminReport);
  $("exportAdminReportInlineBtn")?.addEventListener("click", exportAdminReport);
  $("focusKgBtn")?.addEventListener("click", focusKnowledgeGraph);
  $("newKgRelationBtn")?.addEventListener("click", () => showKgFormModal());
  $("heroVenueBtn")?.addEventListener("click", () => showView("venues"));
  $("saveProfileBtn").addEventListener("click", saveProfile);
  $("submitSessionBtn").addEventListener("click", submitSession);
  $("generateReportBtn")?.addEventListener("click", generateCurrentReport);
  $("loadReportHistoryBtn")?.addEventListener("click", () => openReportHistoryModal(state.reportHistory));
  $("closeReportModalBtn")?.addEventListener("click", closeReportModal);
  $("reportModal")?.addEventListener("click", (event) => {
    if (event.target?.id === "reportModal") closeReportModal();
  });
  $("startGameBtn").addEventListener("click", () => {
    startGame();
  });
  $("durationInput").addEventListener("input", () => {
    if (!state.game.running) {
      const seconds = Number($("durationInput").value) || 60;
      state.game.timeLeft = seconds;
      $("timeLeft").textContent = seconds;
    }
  });
  $("backToTrainingHub")?.addEventListener("click", backToTrainingHub);
  $("cameraBtn").addEventListener("click", openCamera);
  $("exerciseSelect").addEventListener("change", () => {
    state.selectedExercise = $("exerciseSelect").value;
    updateTrainingModeText();
    drawGame();
  });
  $("scoreInput").addEventListener("input", () => {
    state.poseScore = Number($("scoreInput").value);
    $("scoreValue").textContent = $("scoreInput").value;
  });

  window.addEventListener("keydown", (event) => {
    const key = event.key.toLowerCase();
    if (isRunningMode() && (key === " " || key === "arrowup" || key === "w")) {
      setStatus("跑步模块使用摄像头判断动作，请点击或允许“启动 MediaPipe 识别”。", "warn");
      return;
    }
    if (key === "a" || key === "arrowleft") handleAction("left");
    if (key === "d" || key === "arrowright") handleAction("right");
    if (key === "s" || key === "arrowdown") handleAction("duck");
  });
}

async function init() {
  setAuthState(false);
  bindEvents();
  renderProfileAi();
  showView("profile");
  hydrateVenueHeader();
  drawGame();
  await loadExerciseLibrary();
}

window.fitnessApp = {
  chooseExercise,
  enterTraining,
  startGame,
  drawGame,
  openCamera,
  refreshVenueMap: () => state.venueMap?.invalidateSize(),
  refreshVenueLocationAndData,
};

init();
