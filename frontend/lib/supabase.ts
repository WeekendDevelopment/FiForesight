import { createClient } from '@supabase/supabase-js';

// Use `||` (not `??`) so an empty-string env var also falls back to the
// placeholder. In CI / fork PRs these vars are set-but-empty, and `createClient('')`
// throws "supabaseUrl is required" during static prerender of /_not-found.
const url = process.env.NEXT_PUBLIC_SUPABASE_URL || 'https://placeholder.supabase.co';
const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || 'placeholder-anon-key';

export const supabase = createClient(url, key);
