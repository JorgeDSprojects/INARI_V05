import { useEffect, useRef, useState } from "react";
import { wsUrl } from "../api/client";

export interface LiveFrame {
  time: string;
  payload: Record<string, number>;
}

export function useDashboardSocket(dashboardId: string, topics: string[]): Record<string, LiveFrame> {
  const [frames, setFrames] = useState<Record<string, LiveFrame>>({});
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const stoppedRef = useRef(false);

  useEffect(() => {
    if (topics.length === 0) return;
    stoppedRef.current = false;

    const connect = () => {
      const socket = new WebSocket(wsUrl(dashboardId));
      socketRef.current = socket;
      socket.onopen = () => socket.send(JSON.stringify({ subscribe: topics }));
      socket.onmessage = (event) => {
        const frame = JSON.parse(event.data);
        setFrames((prev) => ({ ...prev, [frame.topic]: { time: frame.time, payload: frame.payload } }));
      };
      socket.onclose = () => {
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

  return frames;
}
