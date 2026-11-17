import { SearchView } from "@/components/search/search-view";

export default async function SearchChatPage({ params }: { params: Promise<{ chatId: string }> }) {
  const { chatId } = await params;
  return <SearchView key={chatId} chatId={chatId} />;
}
