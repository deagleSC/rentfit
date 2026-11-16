export const qk = {
  me: () => ["me"] as const,
  cities: () => ["cities"] as const,
  localities: (city: string, geometry = false) => ["localities", city, geometry] as const,
  pois: (city: string, kinds: readonly string[] = []) => ["pois", city, [...kinds]] as const,
};
