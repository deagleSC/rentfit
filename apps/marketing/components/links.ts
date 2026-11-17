// NEXT_PUBLIC_* values are inlined at build time, so each is referenced literally.
export const LANDLORD_APP = process.env.NEXT_PUBLIC_LANDLORD_APP_URL ?? "https://rentfit-landlord.vercel.app";
export const TENANT_APP = process.env.NEXT_PUBLIC_TENANT_APP_URL ?? "https://rentfit-tenant.vercel.app";
