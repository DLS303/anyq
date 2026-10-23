"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { fetchChatPeers, fetchMessages, fetchThreadsPage, openChatThread, sendChat, type ChatPeer } from "@/lib/api";
import { PageNav, useServerPaged } from "@/components/ui/PagedList";
import { ErrorRetry, useAsync, useSubmitLock } from "@/lib/useAsync";
import type { ChatMessage, Locale } from "@/lib/types";
import { useMessages } from "@/lib/i18n";

const MESSAGE_PAGE = 40;

export function ChatApp({ locale, threadId }: { locale: Locale; threadId?: string }) {
  const m = useMessages();
  const { user } = useAuth();
  const sendLock = useSubmitLock();
  const [text, setText] = useState("");
  const [sendError, setSendError] = useState("");
  const [starting, setStarting] = useState(false);
  const [extra, setExtra] = useState<ChatMessage[]>([]);
  const [shown, setShown] = useState(MESSAGE_PAGE);
  const threadPages = useServerPaged(
    user?.email ?? "",
    (page, signal) => (user ? fetchThreadsPage(user.email, page, 20, signal) : Promise.resolve({ items: [], total: 0 })),
    20,
  );
  const threads = threadPages.slice;
  const peersQuery = useAsync(
    (signal) => (user ? fetchChatPeers(signal) : Promise.resolve([] as ChatPeer[])),
    [user?.email],
  );
  const peers = peersQuery.data ?? [];
  const active = threadId || (typeof window !== "undefined" && window.innerWidth >= 768 ? threads[0]?.id : undefined);
  const messagesQuery = useAsync(
    async (signal) => {
      if (!user || !active) return [] as ChatMessage[];
      const result = await fetchMessages(user.email, active, signal);
      return result.messages;
    },
    [user?.email, active],
  );
  useEffect(() => {
    setExtra([]);
    setShown(MESSAGE_PAGE);
  }, [active]);
  const messages = extra.length && messagesQuery.data ? [...messagesQuery.data, ...extra] : (messagesQuery.data ?? []);
  const visible = messages.slice(Math.max(0, messages.length - shown));

  if (!user) {
    return (
      <Link href={`/${locale}/login`} className="btn-ice inline-flex">
        {m.navLogin}
      </Link>
    );
  }

  async function send() {
    if (!user || !active || !text.trim() || sendLock.pending) return;
    const body = text.trim();
    setSendError("");
    await sendLock.run(async () => {
      try {
        const msg = await sendChat(user.email, active, body);
        setExtra((cur) => [...cur, msg]);
        setText("");
        setShown((count) => Math.max(count, MESSAGE_PAGE));
      } catch (err) {
        setSendError(err instanceof Error ? err.message : m.chatSendError);
      }
    });
  }

  async function start(peer: ChatPeer) {
    if (!user || starting) return;
    setStarting(true);
    setSendError("");
    try {
      const thread = await openChatThread(peer.id, peer.full_name);
      await threadPages.reload();
      window.location.assign(`/${locale}/chat/${thread.id}`);
    } catch (err) {
      setSendError(err instanceof Error ? err.message : m.chatSendError);
    } finally {
      setStarting(false);
    }
  }

  const showList = !threadId;
  const showPane = Boolean(threadId) || Boolean(active);

  return (
    <div className="grid min-h-[70dvh] min-w-0 gap-3 md:grid-cols-[260px_1fr]">
      <aside className={`overflow-hidden rounded-2xl border border-ink/10 bg-white/40 ${showList ? "block" : "hidden md:block"}`}>
        {threadPages.loading ? <p className="p-4 text-sm text-ink/50">{m.hubLoading}</p> : null}
        {threadPages.status === "error" ? (
          <div className="p-3">
            <ErrorRetry message={m.listLoadError} retryLabel={m.retry} onRetry={threadPages.reload} />
          </div>
        ) : null}
        {threadPages.status !== "error"
          ? threadPages.slice.map((th) => (
              <Link
                key={th.id}
                href={`/${locale}/chat/${th.id}`}
                className={`block min-h-14 border-b border-ink/10 px-4 py-3.5 text-sm ${th.id === active ? "bg-white" : ""}`}
              >
                {th.title}
              </Link>
            ))
          : null}
        {!threadPages.loading && threadPages.status !== "error" && threadPages.total === 0 ? (
          <div className="grid gap-2 p-4">
            <p className="text-sm text-ink/70">{m.chatEmpty}</p>
            {peers.length === 0 ? <p className="text-sm text-ink/50">{m.chatNoPeers}</p> : null}
            {peers.map((peer) => (
              <button
                key={peer.id}
                type="button"
                className="min-h-12 rounded-full border border-ink/15 px-3 text-left text-sm"
                disabled={starting}
                onClick={() => void start(peer)}
              >
                {m.chatStart} · {peer.full_name}
              </button>
            ))}
          </div>
        ) : null}
        <div className="px-3 pb-3">
          <PageNav
            page={threadPages.page}
            pages={threadPages.pages}
            status={m.pageStatus.replace("{page}", String(threadPages.page + 1)).replace("{pages}", String(threadPages.pages))}
            prevLabel={m.pagePrev}
            nextLabel={m.pageNext}
            onPage={threadPages.setPage}
          />
        </div>
      </aside>
      <section className={`min-h-[60dvh] flex-col rounded-2xl border border-ink/10 bg-white/40 ${showPane && (threadId || active) ? "flex" : "hidden md:flex"}`}>
        <div className="flex items-center gap-2 border-b border-ink/10 px-3 py-2 text-xs text-ink/45">
          {threadId ? (
            <Link href={`/${locale}/chat`} className="py-2 pr-2 text-pine md:hidden">
              ←
            </Link>
          ) : null}
          <span>{m.chatHint}</span>
        </div>
        <div className="grid flex-1 content-start gap-2 overflow-y-auto p-3">
          {messagesQuery.status === "error" ? (
            <ErrorRetry message={m.listLoadError} retryLabel={m.retry} onRetry={messagesQuery.reload} />
          ) : null}
          {messages.length > shown ? (
            <button
              type="button"
              className="min-h-11 text-sm text-pine"
              onClick={() => setShown((count) => count + MESSAGE_PAGE)}
            >
              {m.showEarlier}
            </button>
          ) : null}
          {messagesQuery.loading ? <p className="text-sm text-ink/50">{m.hubLoading}</p> : null}
          {visible.map((msg) => (
            <div
              key={msg.id}
              className={`max-w-[85%] rounded-2xl p-2.5 text-sm ${msg.author_id === user.id ? "ml-auto bg-pine text-paper" : "bg-mist"}`}
            >
              {msg.text}
            </div>
          ))}
        </div>
        {sendError ? <p className="px-3 text-sm text-red-700" role="alert">{sendError}</p> : null}
        {active ? (
          <form
            className="flex gap-2 border-t border-ink/10 p-2"
            onSubmit={(e) => {
              e.preventDefault();
              void send();
            }}
          >
            <input
              className="min-h-11 min-w-0 flex-1 px-3"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={m.message}
            />
            <button className="btn-ice shrink-0 !px-4" disabled={sendLock.pending}>
              {m.send}
            </button>
          </form>
        ) : (
          <p className="hidden p-4 text-sm text-ink/50 md:block">{m.chatPick}</p>
        )}
      </section>
    </div>
  );
}
