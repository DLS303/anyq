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
  const active = threadId || threads[0]?.id;

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
      <Link href={`/${locale}/login`} className="underline">
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

  return (
    <div className="grid md:grid-cols-[260px_1fr] gap-4 min-h-[480px]">
      <aside className="border border-ink/10">
        {threads.map((th) => (
          <Link
            key={th.id}
            href={`/${locale}/chat/${th.id}`}
            className={`block px-3 py-3 text-sm border-b border-ink/10 ${th.id === active ? "bg-white" : ""}`}
          >
            {th.title}
          </Link>
        ))}
        {threads.length === 0 ? <p className="p-3 text-sm text-ink/50">{m.empty}</p> : null}
      </aside>
      <section className="border border-ink/10 flex flex-col">
        <p className="px-4 py-2 text-xs text-ink/45 border-b border-ink/10">{m.chatHint}</p>
        <div className="flex-1 p-4 grid gap-2 content-start overflow-y-auto max-h-[360px]">
          {messages.map((msg) => (
            <div key={msg.id} className={`text-sm max-w-[80%] p-2 ${msg.author_id === user.id ? "ml-auto bg-pine text-paper" : "bg-mist"}`}>
              {msg.text}
            </div>
          ))}
        </div>
        {active ? (
          <form
            className="flex border-t border-ink/10"
            onSubmit={(e) => {
              e.preventDefault();
              send();
            }}
          >
            <input
              className="flex-1 px-3 py-2 bg-transparent"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={m.message}
            />
            <button className="px-4 bg-pine text-paper">{m.send}</button>
          </form>
        ) : null}
      </section>
    </div>
  );
}
