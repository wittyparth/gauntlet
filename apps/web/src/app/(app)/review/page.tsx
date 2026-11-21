"use client";

import { useCallback, useState } from "react";

import { LabelBar } from "@/components/review/label-bar";
import { ReviewItem } from "@/components/review/review-item";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { LoadingRows } from "@/components/shared/loading";
import { PageHeader } from "@/components/shared/page-header";
import { useToast } from "@/components/shared/use-toast";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useReviewItem, useReviewQueue, useSubmitLabel, type LabelResult } from "@/lib/api/hooks/review";
import { useRubricList } from "@/lib/api/hooks/rubrics";

export default function ReviewPage() {
  const rubrics = useRubricList();
  const [picked, setPicked] = useState<string | null>(null);
  const rubric = picked ?? rubrics.data?.items[0]?.id ?? "";
  const queue = useReviewQueue(rubric);
  const [index, setIndex] = useState(0);
  const [reveal, setReveal] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const submit = useSubmitLabel();
  const toast = useToast();

  const items = queue.data?.items ?? [];
  const current = items[index] ?? null;
  const item = useReviewItem(current?.episode_id ?? null, rubric, reveal);
  const done = items.length > 0 && index >= items.length;

  const go = useCallback(
    (to: number) => {
      setIndex(Math.max(0, Math.min(items.length, to)));
      setReveal(false);
    },
    [items.length],
  );
  const onLabel = useCallback(
    (result: LabelResult) => {
      if (!current || submit.isPending) return;
      submit.mutate(
        { episode_id: current.episode_id, rubric_id: rubric, result },
        {
          onSuccess: () => {
            setAnnouncement(`Labelled ${result}, ${index + 1} of ${items.length}`);
            go(index + 1);
          },
          onError: (e) => toast.error(e, "Could not save the label"),
        },
      );
    },
    [current, submit, rubric, index, items.length, go, toast],
  );

  return (
    <>
      <PageHeader
        title="Review"
        breadcrumbs={[{ label: "Quality" }, { label: "Review" }]}
        meta={
          <div className="flex items-center gap-2">
            <Select
              items={(rubrics.data?.items ?? []).map((r) => ({ value: r.id, label: r.title }))}
              value={rubric || null}
              onValueChange={(v) => {
                setPicked(v);
                setIndex(0);
                setReveal(false);
              }}
            >
              <SelectTrigger aria-label="Rubric" className="w-64"><SelectValue placeholder="Choose a rubric" /></SelectTrigger>
              <SelectContent>
                {(rubrics.data?.items ?? []).map((r) => <SelectItem key={r.id} value={r.id}>{r.title}</SelectItem>)}
              </SelectContent>
            </Select>
            {items.length > 0 ? <span className="text-muted-foreground text-sm" data-testid="review-counter">{Math.min(index + 1, items.length)} of {items.length}</span> : null}
          </div>
        }
      />
      <div className="flex flex-col gap-3 p-4">
        {items.length > 0 ? <Progress value={(Math.min(index, items.length) / items.length) * 100} aria-label="Review progress" /> : null}
        {rubrics.error ? <ErrorState error={rubrics.error} onRetry={() => rubrics.refetch()} /> : null}
        {queue.isLoading ? <LoadingRows rows={4} /> : null}
        {queue.error ? <ErrorState error={queue.error} onRetry={() => queue.refetch()} /> : null}
        {queue.data && items.length === 0 ? (
          <EmptyState title="Nothing to review" body="Episodes land here when a judge is unsure, when judges disagree, or when the golden set needs more labels for this rubric." />
        ) : null}
        {done ? <EmptyState title="Queue finished" body="Every item in this queue has been labelled or skipped." /> : null}
        {current ? (
          <ReviewItem item={item.data} loading={item.isLoading} error={item.error} revealed={reveal} onRetry={() => item.refetch()} />
        ) : null}
      </div>
      {items.length > 0 ? (
        <LabelBar
          disabled={!current || submit.isPending}
          onLabel={onLabel}
          onSkip={() => go(index + 1)}
          onNext={() => go(index + 1)}
          onPrev={() => go(index - 1)}
          onToggleJudge={() => setReveal((r) => !r)}
          announcement={announcement}
        />
      ) : null}
    </>
  );
}
