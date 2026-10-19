"use client";

import { Component, createElement, type ReactNode } from "react";

type Props = {
  children?: ReactNode;
  message: string;
  retryLabel: string;
};

type State = { error: Error | null };

export class WidgetBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  render() {
    if (!this.state.error) return this.props.children;
    return createElement(
      "div",
      { role: "alert", className: "border border-ink/10 bg-white/70 p-6 text-center" },
      createElement("p", { className: "text-sm text-ink/70" }, this.props.message),
      createElement(
        "button",
        {
          type: "button",
          className:
            "mt-4 inline-flex min-h-12 items-center justify-center rounded-full bg-pine px-4 text-sm font-medium text-paper",
          onClick: () => this.setState({ error: null }),
        },
        this.props.retryLabel,
      ),
    );
  }
}
