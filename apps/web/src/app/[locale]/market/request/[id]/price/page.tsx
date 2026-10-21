import { MarketOffer } from "@/components/market/MarketOffer";

export default async function PricePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <MarketOffer requestId={id} />;
}
