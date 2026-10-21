"use client";

import { useEffect, useState } from "react";
import { fetchBootstrap } from "./api";

/** Sign-up stays available until bootstrap says REGISTRATION_ENABLED is off. */
export function useRegistrationEnabled() {
  const [enabled, setEnabled] = useState(true);
  useEffect(() => {
    let stop = false;
    fetchBootstrap()
      .then((row) => {
        if (!stop) setEnabled(row.registration_enabled !== false);
      })
      .catch(() => undefined);
    return () => {
      stop = true;
    };
  }, []);
  return enabled;
}
