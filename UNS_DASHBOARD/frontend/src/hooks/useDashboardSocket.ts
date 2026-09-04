import { useEffect, useRef, useState } from "react";
import { wsUrl } from "../api/client";

export interface LiveFrame {
  time: string;
  payload: Record<string, number>;
}

export interface DashboardSocketState {
  frames: Record<string, LiveFrame>;
  wsOpen: boolean;
  lastFrameAt: Record<string, number>;
  connectedAt: number;
}

export function useDashboardSocket(dashboardId: string, topics: string[]): DashboardSocketState {
  const [frames, setFrames] = useState<Record<string, LiveFrame>>({});
  const [wsOpen, setWsOpen] = useState(false);
  const [lastFrameAt, setLastFrameAt] = useState<Record<string, number>>({});
  const [connectedAt, setConnectedAt] = useState(0);
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const stoppedRef = useRef(false);

  useEffect(() => {
    if (topics.length === 0) return;
    stoppedRef.current = false;

    const connect = () => {
      const socket = new WebSocket(wsUrl(dashboardId));
      socketRef.current = socket;
      socket.onopen = () => {
        setWsOpen(true);
        setConnectedAt(Date.now());
        socket.send(JSON.stringify({ subscribe: topics }));
      };
      socket.onmessage = (event) => {
        try {
          const frame = JSON.parse(event.data);
          setFrames((prev) => ({ ...prev, [frame.topic]: { time: frame.time, payload: frame.payload } }));
          setLastFrameAt((prev) => ({ ...prev, [frame.topic]: Date.now() }));
        } catch {
          /* ignore malformed frame */
        }
      };
      socket.onclose = () => {
        setWsOpen(false);
        if (stoppedRef.current) return;
        reconnectTimeoutRef.current = setTimeout(connect, 2000);
      };
    };
    connect();

    return () => {
      stoppedRef.current = true;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      if (socketRef.current) {
        socketRef.current.onclose = null;
        socketRef.current.close();
      }
    };
  }, [dashboardId, topics.join(",")]);

  return { frames, wsOpen, lastFrameAt, connectedAt };
}
