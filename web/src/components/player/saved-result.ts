import { useMemo, useSyncExternalStore } from "react";
import type { AttemptResult } from "@/lib/api/types";

/*
 * The last debrief per case, kept in sessionStorage for this tab, so refresh or back/forward
 * shows the result again instead of an empty player (and never re-submits).
 * Read through useSyncExternalStore: the server snapshot is null, so hydration matches.
 */

const EVENT = "case-lab:saved-result";
const keyFor = (slug: string) => `case-lab:result:${slug}`;

function subscribe(callback: () => void): () => void {
  window.addEventListener("storage", callback);
  window.addEventListener(EVENT, callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener(EVENT, callback);
  };
}

function readRaw(slug: string): string | null {
  try {
    return window.sessionStorage.getItem(keyFor(slug));
  } catch {
    return null; // storage blocked (private mode): the debrief still shows from memory
  }
}

export function saveResult(slug: string, result: AttemptResult): void {
  try {
    window.sessionStorage.setItem(keyFor(slug), JSON.stringify(result));
  } catch {
    // storage blocked or full: nothing to persist, the in-memory result is still on screen
  }
  window.dispatchEvent(new Event(EVENT));
}

export function clearSavedResult(slug: string): void {
  try {
    window.sessionStorage.removeItem(keyFor(slug));
  } catch {
    // storage blocked: nothing was saved
  }
  window.dispatchEvent(new Event(EVENT));
}

export function useSavedResult(slug: string): AttemptResult | null {
  const raw = useSyncExternalStore(subscribe, () => readRaw(slug), () => null);
  return useMemo(() => {
    if (!raw) return null;
    try {
      return JSON.parse(raw) as AttemptResult;
    } catch {
      return null;
    }
  }, [raw]);
}
