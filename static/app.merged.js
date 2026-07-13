const state = {
  user: null,
  dashboard: null,
  assets: {},
  poseLandmarker: null,
  poseModule: null,
  cameraVideo: null,
  cameraStream: null,
  modelReady: false,
  lastVideoTime: -1,
  latestLandmarks: null,
  lastPoseAt: 0,
  poseScore: 82,
  lastPoseActionAt: 0,
  exerciseDurations: {},
  selectedExercise: "拳击挥击",
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
    inputFlash: null,
    action: "待开始",
  },
};

const $ = (id) => document.getElementById(id);
const USER_STORAGE_KEY = "fitflow_user";
const RUNNING_EXERCISES = new Set(["快走", "节奏冲刺"]);
const BOXING_EXERCISES = new Set(["拳击挥击"]);

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

function getExerciseDuration(name = state.selectedExercise) {
  return Number(state.exerciseDurations[name]) || 60;
}

function resetTrainingSession(name = state.selectedExercise) {
  const duration = getExerciseDuration(name);
  state.game.running = false;
  state.game.timeLeft = duration;
  state.game.targets = [];
  state.game.particles = [];
  state.game.lastSpawn = 0;
  state.game.action = "待开始";

  if ($("durationInput")) $("durationInput").value = duration;
  if ($("timeLeft")) $("timeLeft").textContent = duration;
  if ($("currentAction")) $("currentAction").textContent = "待开始";
  if ($("startGameBtn")) {
    $("startGameBtn").textContent = "开始";
    $("startGameBtn").classList.remove("is-running");
  }
}

function stopTrainingSession({ reset = true } = {}) {
  state.game.running = false;

  if (state.cameraStream) {
    state.cameraStream.getTracks().forEach((track) => track.stop());
    state.cameraStream = null;
    state.cameraVideo = null;

    const preview = $("cameraPreview");
    if (preview) {
      preview.srcObject = null;
      preview.classList.remove("active");
    }
  }

  if (reset) resetTrainingSession(state.selectedExercise);
}

function setAuthGate(required) {
  document.body.classList.toggle("auth-required", required);
  document.body.classList.toggle("is-authenticated", !required);
}

function showView(viewId) {
  if (!state.user && viewId !== "profile") viewId = "profile";
  setAuthGate(!state.user);

  if (viewId !== "game") stopTrainingSession();

  document.querySelectorAll(".nav").forEach((item) => {
    item.classList.toggle("active", item.dataset.view === viewId);
  });
  document.querySelectorAll(".view").forEach((item) => {
    item.classList.toggle("active", item.id === viewId);
  });
  if (viewId === "game") {
    const hub = $("trainingHub");
    const workspace = $("trainingWorkspace");
    if (hub && workspace) {
      stopTrainingSession();
      workspace.hidden = true;
      workspace.classList.remove("running-layout", "boxing-layout");
      hub.hidden = false;
    }
  }
  if (viewId === "game" && !$("trainingWorkspace")?.hidden) drawGame();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function setUser(user) {
  state.user = user;
  localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
  setAuthGate(false);
  $("welcome").textContent = `${user.nickname}，欢迎回到虚拟训练关卡`;
  $("userLevel").textContent = user.level;
  $("userPoints").textContent = user.points;
  $("age").value = user.age;
  $("fitnessLevel").value = user.fitness_level;
  $("injuries").value = user.injuries || "";
  $("preference").value = user.preference || "综合训练";
  $("location").value = user.location || "校园东区";
}

function restoreStoredUser() {
  try {
    const cached = JSON.parse(localStorage.getItem(USER_STORAGE_KEY) || "null");
    if (!cached || !cached.id) return false;
    setUser(cached);
    return true;
  } catch (error) {
    localStorage.removeItem(USER_STORAGE_KEY);
    return false;
  }
}

function showAuthNotice(message, tone = "error") {
  const node = $("authNotice");
  if (!node) return;
  node.hidden = false;
  node.textContent = message;
  node.className = `auth-notice ${tone}`.trim();
}

function clearAuthNotice() {
  const node = $("authNotice");
  if (!node) return;
  node.hidden = true;
  node.textContent = "";
  node.className = "auth-notice";
}

function showProfileNotice(message, tone = "success") {
  const node = $("profileNotice");
  if (!node) return;
  node.hidden = false;
  node.textContent = message;
  node.className = `auth-notice profile-notice ${tone}`.trim();
}

function clearProfileNotice() {
  const node = $("profileNotice");
  if (!node) return;
  node.hidden = true;
  node.textContent = "";
  node.className = "auth-notice profile-notice";
}

async function loadDashboard() {
  if (!state.user) return;
  const dashboard = await api(`/api/dashboard?user_id=${state.user.id}`);
  state.dashboard = dashboard;
  $("profileSummary").textContent = dashboard.profile_summary;
  renderTodayPlan(dashboard.today_plan);
  renderAgentFlow(dashboard.agent_flow);
  renderExercises(dashboard.recommendations.exercises);
  renderVenues(dashboard.recommendations.venues);
  renderTips(dashboard.tips);
  renderReport(dashboard.report);
  renderBadges(dashboard.badges);
  renderPointLogs(dashboard.point_logs);
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

function renderVenues(items) {
  $("venueList").classList.remove("empty");
  $("venueList").innerHTML = items.map((item) => `
    <div class="venue-card">
      <strong>${item.name}</strong>
      <span>${item.location} / ${item.open_hours}</span>
      <p>${item.equipment}</p>
      <small>拥挤度 ${item.crowd_index} / 空气指数 ${item.air_quality} / 匹配 ${item.match_score}</small>
      <em>${item.reason || "综合环境指标较均衡"}</em>
    </div>
  `).join("");
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

function renderReport(report) {
  $("reportSummary").textContent = report.summary;
  $("reportInsight").innerHTML = report.count ? `
    <span>训练次数 <b>${report.count}</b></span>
    <span>平均分 <b>${report.average}</b></span>
    <span>优势动作 <b>${report.best_exercise || "-"}</b></span>
    <span>薄弱动作 <b>${report.weak_exercise || "-"}</b></span>
  ` : "";
  renderTrend(report.trend || []);
  $("sessionList").innerHTML = report.sessions.map((item) => `
    <div class="list-item">
      <strong>${item.exercise_name}，${item.score} 分</strong>
      <span>${item.feedback}</span>
      <em>+${item.points} 积分 / ${item.duration} 秒</em>
    </div>
  `).join("");
}

function renderTrend(items) {
  const node = $("trendChart");
  if (!node) return;
  if (!items.length) {
    node.innerHTML = "";
    return;
  }
  node.innerHTML = items.map((item) => `
    <div class="trend-bar" title="${item.exercise_name} ${item.score}分">
      <span style="height:${item.score}%"></span>
      <b>${item.score}</b>
      <small>${item.exercise_name}</small>
    </div>
  `).join("");
}

function renderBadges(items = []) {
  const node = $("badgeList");
  if (!node) return;
  node.classList.remove("empty");
  node.innerHTML = items.map((item) => `
    <div class="badge-card ${item.earned ? "earned" : ""}">
      <strong>${item.icon || "★"} ${item.name}</strong>
      <span>${item.condition_text}</span>
      <em>${item.earned ? "已获得" : `奖励 ${item.reward_points || 0} 积分`}</em>
    </div>
  `).join("");
}

function renderPointLogs(items = []) {
  const node = $("pointLogList");
  if (!node) return;
  node.classList.remove("empty");
  node.innerHTML = items.length ? items.map((item) => `
    <div class="list-item">
      <strong>+${item.points_change} 积分</strong>
      <span>${item.description || item.source_type}</span>
      <em>累计 ${item.total_points}</em>
    </div>
  `).join("") : "完成一次训练后生成积分流水。";
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

function readAuthForm(requireNickname = false) {
  const username = $("username").value.trim();
  const password = $("password").value;
  const nickname = $("nickname").value.trim();

  if (!username) {
    showAuthNotice("请输入用户名", "warn");
    $("username").focus();
    return null;
  }

  if (!password) {
    showAuthNotice("请输入密码", "warn");
    $("password").focus();
    return null;
  }

  if (requireNickname && !nickname) {
    showAuthNotice("请输入昵称", "warn");
    $("nickname").focus();
    return null;
  }

  return { username, password, nickname };
}

function setAuthBusy(isBusy, action = "") {
  const loginBtn = $("loginBtn");
  const registerBtn = $("registerBtn");

  loginBtn.disabled = isBusy;
  registerBtn.disabled = isBusy;
  loginBtn.textContent = isBusy && action === "login" ? "登录中..." : "登录";
  registerBtn.textContent = isBusy && action === "register" ? "注册中..." : "立即注册";
}

async function login() {
  clearAuthNotice();
  const form = readAuthForm();
  if (!form) return;

  setAuthBusy(true, "login");
  try {
    const data = await api("/api/login", {
      method: "POST",
      body: JSON.stringify({
        username: form.username,
        password: form.password,
      }),
    });
    setUser(data.user);
    await loadDashboard();
    showView("dashboard");
  } catch (error) {
    showAuthNotice(error.message || "登录失败，请稍后重试", "error");
  } finally {
    setAuthBusy(false);
  }
}

async function register() {
  clearAuthNotice();
  const form = readAuthForm(true);
  if (!form) return;

  setAuthBusy(true, "register");
  try {
    const data = await api("/api/register", {
      method: "POST",
      body: JSON.stringify({
        username: form.username,
        password: form.password,
        nickname: form.nickname,
      }),
    });
    setUser(data.user);
    await loadDashboard();
    showView("dashboard");
  } catch (error) {
    showAuthNotice(error.message || "注册失败，请稍后重试", "error");
  } finally {
    setAuthBusy(false);
  }
}

function logout() {
  stopTrainingSession();
  localStorage.removeItem(USER_STORAGE_KEY);
  state.user = null;
  state.dashboard = null;
  setAuthGate(true);
  showView("profile");
}

async function saveProfile() {
  if (!state.user) {
    showProfileNotice("请先登录或注册", "warn");
    return;
  }

  const button = $("saveProfileBtn");
  clearProfileNotice();
  button.disabled = true;
  button.textContent = "保存中...";

  try {
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
    renderExercises(data.dashboard.recommendations.exercises);
    renderVenues(data.dashboard.recommendations.venues);
    renderTips(data.dashboard.tips);
    renderReport(data.dashboard.report);
    $("profileSummary").textContent = data.dashboard.profile_summary;
    showProfileNotice("画像已保存，推荐方案已刷新。", "success");
  } catch (error) {
    showProfileNotice(error.message || "保存失败，请稍后重试", "error");
  } finally {
    button.disabled = false;
    button.textContent = "保存画像并刷新推荐";
  }
}

async function submitSession() {
  if (!state.user) return alert("请先登录或注册");
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
  stopTrainingSession();
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
  state.game.timeLeft = Number($("durationInput").value) || 60;
  state.game.action = "待开始";
  $("currentAction").textContent = "待开始";
  $("timeLeft").textContent = state.game.timeLeft;
  $("startGameBtn").textContent = "开始";
  $("startGameBtn").classList.remove("is-running");
  drawGame();
}

function backToTrainingHub() {
  stopTrainingSession();
  const hub = $("trainingHub");
  const workspace = $("trainingWorkspace");
  workspace?.classList.remove("running-layout", "boxing-layout");
  if (workspace) workspace.hidden = true;
  if (hub) hub.hidden = false;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function startGame() {
  state.game.running = true;
  state.game.score = 0;
  state.game.combo = 0;
  state.game.bestCombo = 0;
  const duration = Number($("durationInput").value) || getExerciseDuration();
  state.exerciseDurations[state.selectedExercise] = duration;
  state.game.timeLeft = duration;
  state.game.targets = [];
  state.game.particles = [];
  state.game.lastSpawn = 0;
  state.game.lastFrame = performance.now();
  state.game.action = "准备";
  $("gameResult").textContent = "关卡进行中：用身体或键盘完成左右挥击和下蹲闪避。";
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
  state.game.action = "准备";
  $("startGameBtn").textContent = "训练中";
  $("startGameBtn").classList.add("is-running");
  $("gameResult").textContent = isRunningMode()
    ? "跑步与快走进行中：正在启动摄像头，允许权限后系统会根据摆臂、抬膝和节奏判断运动状态并计算得分。"
    : "关卡进行中：用身体或键盘完成左右挥击和下蹲闪避。";
  requestAnimationFrame(loopGame);
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
  if (state.game.running) requestAnimationFrame(loopGame);
}

function drawGame(now = performance.now()) {
  const canvas = $("gameCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  const delta = Math.min(0.05, (now - state.game.lastFrame) / 1000 || 0.016);
  state.game.lastFrame = now;

  drawWorld(ctx, w, h, now);
  if (state.game.running) {
    state.game.timeLeft = Math.max(0, state.game.timeLeft - delta);
    if (now - state.game.lastSpawn > Math.max(560, 1260 - (state.user?.level || 1) * 32)) {
      spawnTarget();
      state.game.lastSpawn = now;
    }
    updateTargets(delta);
    if (state.game.timeLeft <= 0) finishGame();
  }
  if (state.game.running) drawTargets(ctx, w, h);
  drawPlayer(ctx, w, h, now);
  drawParticles(ctx, delta);
  updateHud();
}

function drawWorld(ctx, w, h, now) {
  if (isRunningMode()) {
    drawRunningWorld(ctx, w, h, now);
    return;
  }
  if (isBoxingMode()) {
    drawBoxingWorld(ctx, w, h, now);
    return;
  }

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
  if (state.latestLandmarks && now - state.lastPoseAt < 900 && drawTrackedPosePlayer(ctx, w, h, state.latestLandmarks)) {
    return;
  }
  if (isRunningMode()) {
    drawRunningPlayer(ctx, w, h, now);
    return;
  }
  if (isBoxingMode()) {
    drawBoxingPlayer(ctx, w, h, now);
    return;
  }

  drawGenericPlayer(ctx, w, h, now);
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

  const leftWrist = point(15);
  const rightWrist = point(16);
  const leftKnee = point(25);
  const rightKnee = point(26);
  const leftAnkle = point(27);
  const rightAnkle = point(28);
  const nose = point(0);

  const shoulderMid = {
    x: (leftShoulder.x + rightShoulder.x) / 2,
    y: (leftShoulder.y + rightShoulder.y) / 2,
  };
  const hipMid = {
    x: (leftHip.x + rightHip.x) / 2,
    y: (leftHip.y + rightHip.y) / 2,
  };
  const torsoHeight = Math.max(0.14, Math.abs(hipMid.y - shoulderMid.y));
  const bodyTilt = clamp((hipMid.x - shoulderMid.x) * 1.8, -0.18, 0.18);
  const crouch = clamp((shoulderMid.y - 0.38) * 0.55 + (0.30 - torsoHeight) * 0.45, 0, 0.16);

  const cx = w * 0.58 + bodyTilt * w;
  const headY = h * (0.33 + crouch * 0.7);
  const shoulderY = h * (0.48 + crouch);
  const hipY = h * (0.66 + crouch * 1.2);
  const torsoTop = [cx, headY + h * 0.075];
  const torsoBottom = [cx, hipY];
  const shoulderJoint = [cx, shoulderY];
  const armLength = w * 0.15;
  const legLength = h * 0.19;

  const followPoint = (joint, target, fallbackX, fallbackY, length, lift = 0) => {
    if (!target) return [joint[0] + fallbackX, joint[1] + fallbackY];
    const dx = clamp((shoulderMid.x - target.x) * w * 1.1, -length, length);
    const dy = clamp((target.y - shoulderMid.y) * h * 1.1 - lift, -length * 0.95, length * 0.95);
    const mag = Math.hypot(dx, dy) || 1;
    const ratio = Math.min(1, length / mag);
    return [joint[0] + dx * ratio, joint[1] + dy * ratio];
  };

  const legPoint = (side, knee, ankle, fallbackX) => {
    if (!knee && !ankle) return [cx + fallbackX, hipY + legLength];
    const reference = ankle || knee;
    const dx = clamp((hipMid.x - reference.x) * w * 1.25, -w * 0.12, w * 0.12);
    const kneeLift = knee ? clamp((hipMid.y - knee.y) * h * 1.7, -h * 0.08, h * 0.11) : 0;
    const dy = clamp((reference.y - hipMid.y) * h * 1.15 + h * 0.09 - kneeLift, h * 0.10, h * 0.25);
    return [cx + dx + side * w * 0.035, hipY + dy];
  };

  const leftHand = followPoint(shoulderJoint, leftWrist, -armLength * 0.82, h * 0.10, armLength);
  const rightHand = followPoint(shoulderJoint, rightWrist, armLength * 0.82, h * 0.10, armLength);
  const leftFoot = legPoint(-1, leftKnee, leftAnkle, -w * 0.09);
  const rightFoot = legPoint(1, rightKnee, rightAnkle, w * 0.09);

  const headOffset = nose ? clamp((shoulderMid.x - nose.x) * w * 0.4, -w * 0.025, w * 0.025) : 0;
  const headX = cx + headOffset;
  const headRadius = Math.max(18, h * 0.055);
  const segments = [
    [torsoTop, torsoBottom],
    [shoulderJoint, leftHand],
    [shoulderJoint, rightHand],
    [torsoBottom, leftFoot],
    [torsoBottom, rightFoot],
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
  for (const [x, y] of [leftHand, rightHand, leftFoot, rightFoot]) {
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

function finishGame() {
  state.game.running = false;
  $("startGameBtn").textContent = "重新开始";
  $("startGameBtn").classList.remove("is-running");
  state.game.action = "已完成";
  $("currentAction").textContent = "已完成";
  $("gameResult").innerHTML = `
    <strong>关卡完成：${state.game.score} 分，最高连击 ${state.game.bestCombo}</strong>
    <p>点击“完成关卡结算”，动作评估智能体会把评分写入报告，图谱推荐智能体会刷新下一轮方案。</p>
  `;
}

function updateHud() {
  $("liveScore").textContent = state.game.score;
  $("comboValue").textContent = state.game.combo;
  $("timeLeft").textContent = Math.ceil(state.game.timeLeft);
  $("scoreValue").textContent = Math.round(state.poseScore);
}

async function preparePoseModel() {
  if (state.modelReady) return;
  setStatus("正在加载 MediaPipe Pose Landmarker...");
  state.poseModule = await import("https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14");
  const { PoseLandmarker, FilesetResolver } = state.poseModule;
  const vision = await FilesetResolver.forVisionTasks(
    "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm",
  );
  state.poseLandmarker = await PoseLandmarker.createFromOptions(vision, {
    baseOptions: {
      modelAssetPath:
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task",
      delegate: "GPU",
    },
    runningMode: "VIDEO",
    numPoses: 1,
  });
  state.modelReady = true;
}

async function openCamera() {
  try {
    if (state.cameraStream && state.cameraVideo) {
      setStatus(
        isRunningMode()
          ? "摄像头识别中：请正对镜头原地快走或慢跑，系统会根据摆臂、抬膝和步频评分。"
          : isBoxingMode()
            ? "摄像头识别中：请正对镜头挥左拳、挥右拳或下蹲闪避，小人会跟随你的动作。"
          : "MediaPipe 识别中：抬左手/右手触发挥击，下蹲触发闪避。",
        "ready",
      );
      return;
    }
    await preparePoseModel();
    const video = $("cameraPreview");
    state.cameraStream = await navigator.mediaDevices.getUserMedia({
      video: { width: 960, height: 540, facingMode: "user" },
      audio: false,
    });
    video.srcObject = state.cameraStream;
    video.classList.add("active");
    state.cameraVideo = video;
    setStatus(
      isRunningMode()
        ? "摄像头识别中：请正对镜头原地快走或慢跑，系统会根据摆臂、抬膝和步频评分。"
        : isBoxingMode()
          ? "摄像头识别中：请正对镜头挥左拳、挥右拳或下蹲闪避，小人会跟随你的动作。"
        : "MediaPipe 识别中：抬左手/右手触发挥击，下蹲触发闪避。",
      "ready",
    );
    requestAnimationFrame(predictPose);
  } catch (error) {
    setStatus("模型或摄像头不可用，已保留键盘演示模式。", "warn");
    alert(`无法启动 MediaPipe：${error.message || "请检查摄像头权限或网络"}`);
  }
}

function predictPose() {
  const video = state.cameraVideo;
  if (!state.poseLandmarker || !video || video.readyState < 2) {
    requestAnimationFrame(predictPose);
    return;
  }

  if (video.currentTime !== state.lastVideoTime) {
    state.lastVideoTime = video.currentTime;
    const result = state.poseLandmarker.detectForVideo(video, performance.now());
    if (result.landmarks?.length) {
      state.latestLandmarks = result.landmarks[0];
      state.lastPoseAt = performance.now();
      updatePoseMetrics(result.landmarks[0]);
      drawGame();
    }
  }
  requestAnimationFrame(predictPose);
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
  }

  const armScore = clamp(Math.abs(state.run.armSwing) * 130, 35, 100);
  const legScore = clamp(Math.abs(state.run.legSwing) * 145 + kneeLift * 320, 35, 100);
  const cadenceScore = state.run.cadence ? clamp(100 - Math.abs(state.run.cadence - 112) * 0.9, 45, 100) : 55;
  const actionScore = clamp(Math.round(confidence * 0.28 + symmetry * 0.18 + armScore * 0.22 + legScore * 0.2 + cadenceScore * 0.12), 40, 100);

  state.poseScore = actionScore;
  state.run.status = state.run.cadence >= 125 ? "快跑" : state.run.cadence >= 75 ? "快走" : armMoving ? "摆臂热身" : "准备";
  $("poseConfidence").textContent = `${confidence}%`;
  $("stabilityScore").textContent = Math.round(symmetry);
  $("scoreValue").textContent = actionScore;
  $("scoreInput").value = actionScore;
  $("currentAction").textContent = state.run.status;
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
  } else if (state.boxing.rightArm > 0.36) {
    state.boxing.status = "右拳";
    handleAction("right", true);
  } else if (state.boxing.crouch > 0.38) {
    state.boxing.status = "下蹲闪避";
    handleAction("duck", true);
  } else {
    state.boxing.status = "防守准备";
  }

  const actionScore = clamp(
    Math.round(confidence * 0.3 + symmetry * 0.2 + Math.max(state.boxing.leftArm, state.boxing.rightArm) * 34 + state.boxing.crouch * 16 + 35),
    40,
    100,
  );
  state.poseScore = actionScore;
  $("poseConfidence").textContent = `${confidence}%`;
  $("stabilityScore").textContent = Math.round(symmetry);
  $("scoreValue").textContent = actionScore;
  $("scoreInput").value = actionScore;
  $("currentAction").textContent = state.boxing.status;
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
    if (rhythm > 0.58) handleAction("step", true);
  } else if (type === "stretch") {
    const reach = clamp(Math.max(leftShoulder.y - leftWrist.y, rightShoulder.y - rightWrist.y) * 1.9 + torsoTilt * 0.35, 0, 1);
    actionScore = clamp(Math.round(confidence * 0.3 + symmetry * 0.18 + reach * 42 + armSpread * 10), 40, 100);
    status = reach > 0.5 ? "\u4f38\u5c55\u5230\u4f4d" : "\u7ee7\u7eed\u62c9\u4f38";
  } else if (type === "core") {
    const stability = clamp(bodyLine, 40, 100);
    actionScore = clamp(Math.round(confidence * 0.28 + symmetry * 0.28 + stability * 0.34 + (1 - torsoTilt) * 10), 40, 100);
    status = stability > 76 ? "\u6838\u5fc3\u7a33\u5b9a" : "\u8c03\u6574\u8eab\u4f53\u76f4\u7ebf";
  } else if (type === "squat") {
    const squatDepth = clamp((150 - kneeAngle) / 70 + hipDrop * 0.45, 0, 1);
    const kneeControl = clamp(100 - Math.abs(leftKnee.x - leftAnkle.x) * 170 - Math.abs(rightKnee.x - rightAnkle.x) * 170, 40, 100);
    actionScore = clamp(Math.round(confidence * 0.25 + symmetry * 0.17 + squatDepth * 38 + kneeControl * 0.2), 40, 100);
    status = squatDepth > 0.55 ? "\u6df1\u8e72\u5230\u4f4d" : "\u4e0b\u8e72\u51c6\u5907";
    if (squatDepth > 0.55) handleAction("duck", true);
  } else {
    const generalMotion = clamp((armRaise + armSpread + legSpread) / 3, 0, 1);
    actionScore = clamp(Math.round(confidence * 0.32 + symmetry * 0.24 + generalMotion * 44), 40, 100);
    status = generalMotion > 0.45 ? "\u52a8\u4f5c\u8ddf\u968f" : "\u8bc6\u522b\u4e2d";
  }

  state.poseScore = actionScore;
  $("poseConfidence").textContent = `${confidence}%`;
  $("stabilityScore").textContent = Math.round(symmetry);
  $("scoreValue").textContent = actionScore;
  $("scoreInput").value = actionScore;
  $("currentAction").textContent = status;
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

function bindEvents() {
  document.querySelectorAll(".nav").forEach((button) => {
    button.addEventListener("click", () => showView(button.dataset.view));
  });
  document.querySelectorAll(".game-card").forEach((card) => {
    card.addEventListener("click", () => chooseExercise(card.dataset.exercise));
  });

  $("railLoginBtn").addEventListener("click", () => {
    $("username").value = "demo";
    $("password").value = "123456";
    $("nickname").value = "李同学";
    login();
  });
  $("homeReturnBtn")?.addEventListener("click", () => showView(state.user ? "dashboard" : "profile"));
  $("logoutBtn")?.addEventListener("click", logout);

  $("topCameraBtn")?.addEventListener("click", () => {
    showView("game");
    enterTraining($("exerciseSelect")?.value || "拳击挥击");
    openCamera();
  });
  $("connectionBtn").addEventListener("click", () => {
    showView("game");
    enterTraining($("exerciseSelect")?.value || "拳击挥击");
    openCamera();
  });
  $("browseGamesBtn").addEventListener("click", () => {
    document.getElementById("gameLobby")?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  $("heroStartBtn").addEventListener("click", () => {
    chooseExercise("拳击挥击");
  });
  $("loginBtn").addEventListener("click", login);
  $("registerBtn").addEventListener("click", register);
  ["username", "password", "nickname"].forEach((id) => {
    $(id)?.addEventListener("input", clearAuthNotice);
  });
  $("saveProfileBtn").addEventListener("click", saveProfile);
  ["age", "fitnessLevel", "injuries", "preference", "location"].forEach((id) => {
    $(id)?.addEventListener("input", clearProfileNotice);
    $(id)?.addEventListener("change", clearProfileNotice);
  });
  $("submitSessionBtn").addEventListener("click", submitSession);
  $("startGameBtn").addEventListener("click", () => {
    startGame();
    openCamera();
  });
  $("durationInput").addEventListener("input", () => {
    if (!state.game.running) {
      const seconds = Number($("durationInput").value) || 60;
      state.exerciseDurations[state.selectedExercise] = seconds;
      state.game.timeLeft = seconds;
      $("timeLeft").textContent = seconds;
    }
  });
  $("backToTrainingHub")?.addEventListener("click", backToTrainingHub);
  $("cameraBtn").addEventListener("click", openCamera);
  $("exerciseSelect").addEventListener("change", () => {
    stopTrainingSession();
    state.selectedExercise = $("exerciseSelect").value;
    updateTrainingModeText();
    resetTrainingSession(state.selectedExercise);
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
  bindEvents();
  drawGame();
  await loadExerciseLibrary();

  if (restoreStoredUser()) {
    try {
      await loadDashboard();
      showView("dashboard");
      return;
    } catch (error) {
      localStorage.removeItem(USER_STORAGE_KEY);
      state.user = null;
    }
  }

  setAuthGate(true);
  showView("profile");
}

window.fitnessApp = {
  chooseExercise,
  enterTraining,
  startGame,
  drawGame,
  openCamera,
};

init();
