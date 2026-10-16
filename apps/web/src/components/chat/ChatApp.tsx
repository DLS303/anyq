"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { fetchMessages, fetchThreads, sendChat } from "@/lib/api";
import type { ChatMessage, ChatThread, Locale } from "@/lib/types";
import { t } from "@/i18n/messages";

export function ChatApp({ locale, threadId }: { locale: Locale; threadId?: string }) {
  const m = t(locale);
  const { user } = useAuth();
  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [text, setText] = useState("");
  const active = threadId || (typeof window !== "undefined" && window.innerWidth >= 768 ? threads[0]?.id : undefined);

  useEffect(() => {
    if (!user) return;
    fetchThreads(user.email).then(setThreads).catch(() => setThreads([]));
  }, [user]);

  useEffect(() => {
    if (!user || !active) return;
    fetchMessages(user.email, active)
      .then((r) => setMessages(r.messages))
      .catch(() => setMessages([]));
  }, [user, active]);

  if (!user) {
    return (
      <Link href={`/${locale}/login`} className="btn-ice inline-flex">
        {m.navLogin}
      </Link>
    );
  }

  async function send() {
    if (!user || !active || !text.trim()) return;
    const msg = await sendChat(user.email, active, text.trim());
    setMessages((cur) => [...cur, msg]);
    setText("");
  }

  const showList = !threadId;
  const showPane = Boolean(threadId) || Boolean(active);

  return (
    <div className="grid md:grid-cols-[260px_1fr] gap-3 min-h-[70dvh]">
      <aside className={`border border-ink/10 rounded-2xl overflow-hidden bg-white/40 ${showList ? "block" : "hidden md:block"}`}>
        {threads.map((th) => (
          <Link
            key={th.id}
            href={`/${locale}/chat/${th.id}`}
            className={`block px-4 py-3.5 text-sm border-b border-ink/10 min-h-14 ${th.id === active ? "bg-white" : ""}`}
          >
            {th.title}
          </Link>
        ))}
        {threads.length === 0 ? <p className="p-4 text-sm text-ink/50">{m.empty}</p> : null}
      </aside>
      <section className={`border border-ink/10 rounded-2xl flex flex-col bg-white/40 min-h-[60dvh] ${showPane && (threadId || active) ? "flex" : "hidden md:flex"}`}>
        <div className="px-3 py-2 text-xs text-ink/45 border-b border-ink/10 flex items-center gap-2">
          {threadId ? (
            <Link href={`/${locale}/chat`} className="md:hidden text-pine py-2 pr-2">
              ←
            </Link>
          ) : null}
          <span>{m.chatHint}</span>
        </div>
        <div className="flex-1 p-3 grid gap-2 content-start overflow-y-auto">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`text-sm max-w-[85%] p-2.5 rounded-2xl ${msg.author_id === user.id ? "ml-auto bg-pine text-paper" : "bg-mist"}`}
            >
              {msg.text}
            </div>
          ))}
        </div>
        {active ? (
          <form
            className="flex border-t border-ink/10 p-2 gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              send();
            }}
          >
            <input
              className="flex-1 px-3 min-h-11"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={m.message}
            />
            <button className="btn-ice !px-4 shrink-0">{m.send}</button>
          </form>
        ) : (
          <p className="p-4 text-sm text-ink/50 hidden md:block">Выберите диалог</p>
        )}
      </section>
    </div>
  );
}
