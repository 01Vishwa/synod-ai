import { createBrowserClient } from '@supabase/ssr';

export const supabase = createBrowserClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
);

supabase.auth.onAuthStateChange((event, session) => {
  if (event === "SIGNED_OUT" || (event === "TOKEN_REFRESHED" && !session)) {
    window.location.href = "/?auth=required";
  }
});
