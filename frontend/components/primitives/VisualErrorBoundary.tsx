"use client";

/**
 * Per-visual error boundary -- Suspense alone isn't enough to isolate a
 * failing endpoint; without this, a thrown fetch error inside one async
 * server component would blank the whole page. Each visual gets its own
 * instance so a bad filter combination on one card never takes down the
 * others.
 */

import { Component, type ReactNode } from "react";
import { ErrorCard } from "./ErrorCard";

interface Props {
  title: string;
  span?: number;
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class VisualErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  render() {
    if (this.state.error) {
      const message =
        (this.state.error as any)?.detail ?? this.state.error.message ?? "Something went wrong.";
      return <ErrorCard title={this.props.title} message={message} span={this.props.span} />;
    }
    return this.props.children;
  }
}
