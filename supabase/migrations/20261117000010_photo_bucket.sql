-- Private bucket for listing photos (backend plan §8.1). The bucket itself enforces the 5 MB limit
-- and image types, so a signed upload URL cannot be used to store anything else. No storage policies:
-- only the API (service key) signs uploads and downloads.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('listing-photos', 'listing-photos', false, 5242880, array['image/webp', 'image/jpeg', 'image/png'])
on conflict (id) do update
  set public = false, file_size_limit = excluded.file_size_limit, allowed_mime_types = excluded.allowed_mime_types;
