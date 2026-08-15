"use client";

import { useEffect, useEffectEvent, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { websocketUrl } from "@/lib/api";
import type { ChainSnapshot, UnderlyingQuote } from "@/lib/types";

interface StreamEnvelope<T> {
  channel: string;
  payload: T | null;
  status?: "ok" | "degraded";
  message?: string;
}

interface StreamStatus {
  state: "idle" | "connecting" | "connected" | "degraded";
  message?: string;
}

interface UseMarketStreamsOptions {
  enableQuotes?: boolean;
  enableChain?: boolean;
}

interface SharedStream {
  key: string;
  url: string;
  socket?: WebSocket;
  subscribers: number;
  messageListeners: Set<(message: MessageEvent) => void>;
  errorListeners: Set<() => void>;
  openListeners: Set<() => void>;
  closeListeners: Set<(willRetry: boolean) => void>;
  releaseTimer?: ReturnType<typeof setTimeout>;
  reconnectTimer?: ReturnType<typeof setTimeout>;
  reconnectAttempts: number;
}

const idleStatus: StreamStatus = { state: "idle" };
const sharedStreams = new Map<string, SharedStream>();
const reconnectDelaysMs = [250, 1_000, 3_000] as const;

function parseStreamEnvelope<T>(data: unknown): StreamEnvelope<T> {
  const parsed = JSON.parse(String(data)) as unknown;
  if (!parsed || typeof parsed !== "object" || !("payload" in parsed)) {
    throw new Error("invalid stream envelope");
  }
  const envelope = parsed as StreamEnvelope<T>;
  if (envelope.payload !== null && typeof envelope.payload !== "object") {
    throw new Error("invalid stream payload");
  }
  return envelope;
}

function connectSharedStream(stream: SharedStream) {
  const socket = new WebSocket(stream.url);
  stream.socket = socket;

  socket.onopen = () => {
    if (stream.socket !== socket) return;
    stream.reconnectAttempts = 0;
    for (const listener of stream.openListeners) {
      listener();
    }
  };
  socket.onmessage = (message) => {
    if (stream.socket !== socket) return;
    for (const listener of stream.messageListeners) {
      listener(message);
    }
  };
  socket.onerror = () => {
    if (stream.socket !== socket) return;
    for (const listener of stream.errorListeners) {
      listener();
    }
  };
  socket.onclose = () => {
    if (stream.socket !== socket) return;
    stream.socket = undefined;
    const willRetry = stream.subscribers > 0 && stream.reconnectAttempts < reconnectDelaysMs.length;
    for (const listener of stream.closeListeners) {
      listener(willRetry);
    }
    if (!willRetry) return;

    const delay = reconnectDelaysMs[stream.reconnectAttempts];
    stream.reconnectAttempts += 1;
    stream.reconnectTimer = setTimeout(() => {
      stream.reconnectTimer = undefined;
      if (stream.subscribers > 0 && sharedStreams.get(stream.key) === stream) {
        connectSharedStream(stream);
      }
    }, delay);
  };
}

function getSharedStream(key: string, url: string) {
  const current = sharedStreams.get(key);
  if (current) {
    if (current.releaseTimer) {
      clearTimeout(current.releaseTimer);
      current.releaseTimer = undefined;
    }
    current.subscribers += 1;
    return current;
  }

  const stream: SharedStream = {
    key,
    url,
    subscribers: 1,
    messageListeners: new Set(),
    errorListeners: new Set(),
    openListeners: new Set(),
    closeListeners: new Set(),
    reconnectAttempts: 0,
  };

  sharedStreams.set(key, stream);
  connectSharedStream(stream);
  return stream;
}

function subscribeToSharedStream(
  stream: SharedStream,
  listeners: {
    onMessage: (message: MessageEvent) => void;
    onError: () => void;
    onOpen: () => void;
    onClose: (willRetry: boolean) => void;
  }
) {
  stream.messageListeners.add(listeners.onMessage);
  stream.errorListeners.add(listeners.onError);
  stream.openListeners.add(listeners.onOpen);
  stream.closeListeners.add(listeners.onClose);

  return () => {
    stream.messageListeners.delete(listeners.onMessage);
    stream.errorListeners.delete(listeners.onError);
    stream.openListeners.delete(listeners.onOpen);
    stream.closeListeners.delete(listeners.onClose);
  };
}

function releaseSharedStream(key: string) {
  const stream = sharedStreams.get(key);
  if (!stream) {
    return;
  }

  stream.subscribers = Math.max(0, stream.subscribers - 1);
  if (stream.subscribers > 0 || stream.releaseTimer) {
    return;
  }

  stream.releaseTimer = setTimeout(() => {
    const current = sharedStreams.get(key);
    if (!current || current.subscribers > 0) {
      return;
    }
    sharedStreams.delete(key);
    if (current.reconnectTimer) {
      clearTimeout(current.reconnectTimer);
    }
    current.socket?.close();
  }, 0);
}

export function __resetSharedMarketStreamsForTests() {
  for (const [key, stream] of sharedStreams.entries()) {
    if (stream.releaseTimer) {
      clearTimeout(stream.releaseTimer);
    }
    if (stream.reconnectTimer) {
      clearTimeout(stream.reconnectTimer);
    }
    stream.subscribers = 0;
    sharedStreams.delete(key);
    stream.socket?.close();
  }
}

export function useMarketStreams(symbol: string, expiration?: string, options: UseMarketStreamsOptions = {}) {
  const { enableQuotes = true, enableChain = true } = options;
  const queryClient = useQueryClient();
  const [quoteStatus, setQuoteStatus] = useState<StreamStatus>(idleStatus);
  const [chainStatus, setChainStatus] = useState<StreamStatus>(idleStatus);

  const onQuoteMessage = useEffectEvent((message: MessageEvent) => {
    let envelope: StreamEnvelope<UnderlyingQuote>;
    try {
      envelope = parseStreamEnvelope<UnderlyingQuote>(message.data);
    } catch {
      setQuoteStatus({ state: "degraded", message: "Ignored a malformed quote-stream message." });
      return;
    }
    if (envelope.payload) {
      queryClient.setQueryData(["summary", symbol], envelope.payload);
      setQuoteStatus({ state: "connected" });
      return;
    }
    setQuoteStatus({ state: "degraded", message: envelope.message });
  });

  const onChainMessage = useEffectEvent((message: MessageEvent) => {
    let envelope: StreamEnvelope<ChainSnapshot>;
    try {
      envelope = parseStreamEnvelope<ChainSnapshot>(message.data);
    } catch {
      setChainStatus({ state: "degraded", message: "Ignored a malformed chain-stream message." });
      return;
    }
    if (envelope.payload) {
      queryClient.setQueryData(["chain", symbol, expiration], envelope.payload);
      queryClient.setQueryData(["chain", symbol, envelope.payload.selected_expiration], envelope.payload);
      setChainStatus({ state: "connected" });
      return;
    }
    setChainStatus({ state: "degraded", message: envelope.message });
  });

  useEffect(() => {
    if (!enableQuotes) {
      setQuoteStatus(idleStatus);
      return;
    }

    setQuoteStatus({ state: "connecting" });
    const quoteKey = `quotes:${symbol}`;
    const quoteStream = getSharedStream(quoteKey, websocketUrl(`/ws/quotes/${symbol}`));
    const unsubscribe = subscribeToSharedStream(quoteStream, {
      onMessage: onQuoteMessage,
      onError: () => {
        setQuoteStatus({ state: "degraded", message: "Quote refresh is unavailable for the active symbol." });
      },
      onOpen: () => {
        setQuoteStatus({ state: "connected" });
      },
      onClose: (willRetry) => {
        setQuoteStatus({
          state: "degraded",
          message: willRetry
            ? "Quote stream disconnected; retrying with a bounded backoff."
            : "Quote stream disconnected after the retry limit.",
        });
      },
    });

    return () => {
      unsubscribe();
      releaseSharedStream(quoteKey);
      setQuoteStatus(idleStatus);
    };
  }, [enableQuotes, symbol]);

  useEffect(() => {
    if (!enableChain) {
      setChainStatus(idleStatus);
      return;
    }

    setChainStatus({ state: "connecting" });
    const chainPath = expiration
      ? `/ws/chains/${symbol}?expiration=${encodeURIComponent(expiration)}`
      : `/ws/chains/${symbol}`;
    const chainKey = `chains:${symbol}:${expiration ?? ""}`;
    const chainStream = getSharedStream(chainKey, websocketUrl(chainPath));
    const unsubscribe = subscribeToSharedStream(chainStream, {
      onMessage: onChainMessage,
      onError: () => {
        setChainStatus({ state: "degraded", message: "Chain refresh is unavailable for the active symbol." });
      },
      onOpen: () => {
        setChainStatus({ state: "connected" });
      },
      onClose: (willRetry) => {
        setChainStatus({
          state: "degraded",
          message: willRetry
            ? "Chain stream disconnected; retrying with a bounded backoff."
            : "Chain stream disconnected after the retry limit.",
        });
      },
    });

    return () => {
      unsubscribe();
      releaseSharedStream(chainKey);
      setChainStatus(idleStatus);
    };
  }, [enableChain, expiration, symbol]);

  return { quoteStatus, chainStatus };
}
