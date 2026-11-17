export const qk = {
  me: () => ["me"] as const,
  cities: () => ["cities"] as const,
  localities: (city: string, geometry = false) => ["localities", city, geometry] as const,
  pois: (city: string, kinds: readonly string[] = []) => ["pois", city, [...kinds]] as const,
  chats: () => ["chats"] as const,
  chat: (id: string) => ["chats", id] as const,
  listing: (id: string, poi?: string) => ["listing", id, poi ?? null] as const,
  shortlist: () => ["shortlist"] as const,
  saved: () => ["saved-searches"] as const,
  enquiries: (role: "tenant" | "landlord") => ["enquiries", role] as const,
  enquiry: (id: string) => ["enquiry", id] as const,
  notifications: () => ["notifications"] as const,
};
