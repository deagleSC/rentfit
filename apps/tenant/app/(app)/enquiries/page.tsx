"use client";

import { messageFor } from "@rentfit/api-client";
import { PageHeader } from "@rentfit/ui/blocks/dashboard-layout";
import { EnquiryConversation, EnquiryList, type ThreadMessage, type ThreadSummary } from "@rentfit/ui/blocks/enquiry-thread";
import { EmptyState, ErrorState, PageSkeleton } from "@rentfit/ui/blocks/states";
import { MessageSquare } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { toast } from "sonner";

import { inr, useEnquiries, useEnquiry, useReply } from "@/lib/homes";

function Thread({ id }: { id: string }) {
  const q = useEnquiry(id);
  const reply = useReply(id);
  if (q.isError) return <ErrorState message={messageFor(q.error)} />;
  if (q.isPending) return <PageSkeleton />;
  const e = q.data.enquiry;
  return (
    <EnquiryConversation
      title={<Link href={`/listings/${e.listing_id}`} className="hover:underline">{e.listing_title}</Link>}
      subtitle={`${e.locality} · ${inr(e.rent)} · with ${e.other_name}`}
      messages={q.data.messages as ThreadMessage[]}
      sending={reply.isPending}
      onSend={(b) => reply.mutate(b, { onError: (err) => toast.error(messageFor(err)) })}
    />
  );
}

function Inbox() {
  const q = useEnquiries();
  const params = useSearchParams();
  const router = useRouter();
  if (q.isError) return <ErrorState message={messageFor(q.error)} />;
  if (q.isPending) return <PageSkeleton />;
  const selected = params.get("id") ?? q.data[0]?.id ?? null;
  return (
    <>
      <PageHeader title="Enquiries" description="Your conversations with landlords." />
      {q.data.length === 0 ? (
        <EmptyState icon={<MessageSquare />} title="No enquiries yet" description="Send one from a listing's page." />
      ) : (
        <div className="grid gap-4 md:grid-cols-[300px_1fr]">
          <EnquiryList items={q.data as ThreadSummary[]} selected={selected} onSelect={(id) => router.replace(`/enquiries?id=${id}`)} />
          {selected && <Thread key={selected} id={selected} />}
        </div>
      )}
    </>
  );
}

export default function EnquiriesPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <Inbox />
    </Suspense>
  );
}
