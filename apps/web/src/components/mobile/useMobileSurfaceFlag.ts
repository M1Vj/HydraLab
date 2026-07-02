import { useEffect, useState } from "react";
import { api, type SettingsResponse } from "../../lib/api";
import { booleanPreference } from "../../workspace/panels/settingsController";

/**
 * Phase-3 mobile surface feature flag. Reuses the EXISTING settings contract
 * (`GET /api/settings` workspace preferences) — no new backend route. Default OFF so
 * the desktop workbench path is byte-for-byte unchanged until a maintainer opts in.
 */
export const PHASE3_MOBILE_FLAG_KEY = "phase3_mobile_surface_enabled";

export function usePhase3MobileSurfaceEnabled(): boolean {
  const [enabled, setEnabled] = useState(false);
  useEffect(() => {
    let active = true;
    api
      .get<SettingsResponse>("/api/settings")
      .then((data) => {
        if (active) setEnabled(booleanPreference(data.workspace_preferences, PHASE3_MOBILE_FLAG_KEY, false));
      })
      .catch(() => {
        // Fail closed: any error resolving settings keeps the desktop path.
        if (active) setEnabled(false);
      });
    return () => {
      active = false;
    };
  }, []);
  return enabled;
}
