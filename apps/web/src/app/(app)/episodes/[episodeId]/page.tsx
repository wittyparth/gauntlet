"use client";

import { use } from "react";

import { EpisodeView } from "@/components/episode/episode-view";

export default function EpisodePage({ params }: { params: Promise<{ episodeId: string }> }) {
  const { episodeId } = use(params);
  return <EpisodeView episodeId={episodeId} />;
}
