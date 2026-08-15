import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";

import { __resetSharedMarketStreamsForTests, useMarketStreams } from "@/hooks/use-market-streams";

class MockWebSocket {
  static instances: MockWebSocket[] = [];

  url: string;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onopen: ((event: Event) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  close() {
    this.onclose?.({} as CloseEvent);
  }

  emitMessage(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent);
  }

  emitRaw(data: string) {
    this.onmessage?.({ data } as MessageEvent);
  }
}

let queryClient: QueryClient;

function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

function Harness({
  symbol,
  expiration,
  enableQuotes,
  enableChain,
}: {
  symbol: string;
  expiration?: string;
  enableQuotes?: boolean;
  enableChain?: boolean;
}) {
  const { quoteStatus, chainStatus } = useMarketStreams(symbol, expiration, { enableQuotes, enableChain });
  return (
    <div>
      <div data-testid="quote-state">{quoteStatus.state}</div>
      <div data-testid="quote-message">{quoteStatus.message ?? ""}</div>
      <div data-testid="chain-state">{chainStatus.state}</div>
      <div data-testid="chain-message">{chainStatus.message ?? ""}</div>
    </div>
  );
}

beforeEach(() => {
  queryClient = new QueryClient();
  MockWebSocket.instances = [];
  __resetSharedMarketStreamsForTests();
  vi.stubGlobal("WebSocket", MockWebSocket as unknown as typeof WebSocket);
});

afterEach(() => {
  cleanup();
  __resetSharedMarketStreamsForTests();
  vi.unstubAllGlobals();
});

test("only the active symbol opens refresh streams by default", () => {
  render(<Harness symbol="SPY" expiration="2026-04-17" />, { wrapper });

  expect(MockWebSocket.instances).toHaveLength(2);
  expect(MockWebSocket.instances[0].url).toContain("/ws/quotes/SPY");
  expect(MockWebSocket.instances[1].url).toContain("/ws/chains/SPY?expiration=2026-04-17");
  expect(MockWebSocket.instances.some((socket) => socket.url.includes("AAPL"))).toBe(false);
  expect(MockWebSocket.instances.some((socket) => socket.url.includes("QQQ"))).toBe(false);
});

test("degraded websocket messages stay non-fatal and surface a warning", async () => {
  render(<Harness symbol="SPY" expiration="2026-04-17" />, { wrapper });

  act(() => {
    MockWebSocket.instances[1].emitMessage({
      channel: "chains",
      payload: null,
      status: "degraded",
      message: "Subscription-limited chain refresh",
    });
  });

  await waitFor(() => {
    expect(screen.getByTestId("chain-state")).toHaveTextContent("degraded");
  });
  expect(screen.getByTestId("chain-message")).toHaveTextContent("Subscription-limited chain refresh");
});

test("disabled chain refresh does not open a chain websocket", () => {
  render(<Harness symbol="SPY" expiration="2026-04-17" enableChain={false} />, { wrapper });

  expect(MockWebSocket.instances).toHaveLength(1);
  expect(MockWebSocket.instances[0].url).toContain("/ws/quotes/SPY");
});

test("duplicate subscribers share the same quote and chain sockets", () => {
  render(
    <>
      <Harness symbol="SPY" expiration="2026-04-17" />
      <Harness symbol="SPY" expiration="2026-04-17" />
    </>,
    { wrapper }
  );

  expect(MockWebSocket.instances).toHaveLength(2);
  expect(MockWebSocket.instances[0].url).toContain("/ws/quotes/SPY");
  expect(MockWebSocket.instances[1].url).toContain("/ws/chains/SPY?expiration=2026-04-17");
});

test("malformed stream messages are ignored and surfaced as degraded", async () => {
  render(<Harness symbol="SPY" enableChain={false} />, { wrapper });

  act(() => MockWebSocket.instances[0].emitRaw("not-json"));

  await waitFor(() => expect(screen.getByTestId("quote-state")).toHaveTextContent("degraded"));
  expect(screen.getByTestId("quote-message")).toHaveTextContent("malformed");
});

test("disconnect retries are bounded", () => {
  vi.useFakeTimers();
  render(<Harness symbol="SPY" enableChain={false} />, { wrapper });

  for (let attempt = 0; attempt < 4; attempt += 1) {
    act(() => {
      MockWebSocket.instances.at(-1)?.close();
      vi.runOnlyPendingTimers();
    });
  }

  expect(MockWebSocket.instances).toHaveLength(4);
  expect(screen.getByTestId("quote-message")).toHaveTextContent("retry limit");
  vi.useRealTimers();
});
