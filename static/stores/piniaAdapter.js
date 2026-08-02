let activePinia = null;

export function createPinia() {
  return {
    _stores: new Map(),
  };
}

export function setActivePinia(pinia) {
  activePinia = pinia;
  return pinia;
}

function patchState(target, patch) {
  Object.entries(patch).forEach(([key, value]) => {
    if (
      value &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      target[key] &&
      typeof target[key] === "object" &&
      !Array.isArray(target[key])
    ) {
      patchState(target[key], value);
    } else {
      target[key] = value;
    }
  });
}

export function defineStore(id, options = {}) {
  return function useStore(pinia = activePinia) {
    if (!pinia) throw new Error("Pinia has not been initialized");
    if (!pinia._stores.has(id)) {
      const store = options.state ? options.state() : {};
      Object.defineProperty(store, "$id", { value: id });
      Object.defineProperty(store, "$patch", {
        value(patch) {
          if (typeof patch === "function") {
            patch(store);
            return;
          }
          patchState(store, patch || {});
        },
      });
      Object.defineProperty(store, "$reset", {
        value() {
          const nextState = options.state ? options.state() : {};
          Object.keys(store).forEach((key) => {
            if (!key.startsWith("$")) delete store[key];
          });
          patchState(store, nextState);
        },
      });
      Object.entries(options.actions || {}).forEach(([name, action]) => {
        store[name] = action.bind(store);
      });
      pinia._stores.set(id, store);
    }
    return pinia._stores.get(id);
  };
}
