import { createPinia, defineStore, setActivePinia } from "./piniaAdapter.js";

export const pinia = setActivePinia(createPinia());

export const useAppStore = defineStore("fitnessApp", {
  state: () => ({
    user: null,
    accessToken: sessionStorage.getItem("fitness_access_token") || "",
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
  }),
  actions: {
    setSession(session) {
      this.accessToken = session.access_token;
      this.user = session.user;
      sessionStorage.setItem("fitness_access_token", session.access_token);
      sessionStorage.setItem("fitness_user", JSON.stringify(session.user));
    },
    setUser(user) {
      this.user = user;
      sessionStorage.setItem("fitness_user", JSON.stringify(user));
    },
    clearSession() {
      this.user = null;
      this.accessToken = "";
      this.dashboard = null;
      this.reportHistory = [];
      sessionStorage.removeItem("fitness_access_token");
      sessionStorage.removeItem("fitness_user");
    },
  },
});

export const state = useAppStore(pinia);
