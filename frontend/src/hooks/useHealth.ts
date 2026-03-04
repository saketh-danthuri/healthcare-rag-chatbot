"use client";

import { useState, useEffect, useCallback } from "react";
import type { HealthStatus } from "@/lib/types";
import { api } from "@/lib/api";
import { HEALTH_POLL_INTERVAL } from "@/lib/constants";

interface UseHealthReturn {
  health: HealthStatus | null;
  isChecking: boolean;
  checkNow: () => void;
}

export function useHealth(): UseHealthReturn {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [isChecking, setIsChecking] = useState(false);

  const checkHealth = useCallback(async () => {
    setIsChecking(true);
    try {
      const status = await api.getHealth();
      setHealth(status);
    } catch {
      setHealth({
        status: "offline",
        version: "unknown",
        search_connected: false,
        documents_indexed: 0,
      });
    } finally {
      setIsChecking(false);
    }
  }, []);

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, HEALTH_POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [checkHealth]);

  return { health, isChecking, checkNow: checkHealth };
}
