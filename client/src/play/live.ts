// The live feed socket (UX §7). Events arrive here and over HTTP both; the caller de-duplicates
// on event id, so a reconnect that refetches the gap can never show anything twice.

import { useEffect, useRef, useState } from "react";
import type { FeedEvent } from "../api";

export type Link = "connecting" | "live" | "offline";

const RETRY_MS = 4000;

export function useLive(token: string, onEvent: (event: FeedEvent) => void): Link {
  const [link, setLink] = useState<Link>("connecting");
  // The callback changes on every render; the socket must not.
  const sink = useRef(onEvent);
  sink.current = onEvent;

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;
    let closed = false;

    function open() {
      const scheme = location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${scheme}://${location.host}/v1/stream?token=${encodeURIComponent(token)}`);
      socket.onopen = () => setLink("live");
      socket.onmessage = (message) => {
        const frame = JSON.parse(message.data);
        if (frame.op === "event") sink.current(frame.event as FeedEvent);
      };
      socket.onclose = () => {
        setLink("offline");
        if (!closed) retry = setTimeout(open, RETRY_MS);
      };
      socket.onerror = () => socket?.close();
    }

    open();
    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      socket?.close();
    };
  }, [token]);

  return link;
}
