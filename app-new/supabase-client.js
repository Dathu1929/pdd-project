// ====================================================================
// SUPABASE JAVASCRIPT CLIENT & BACKEND SERVICE
// Replaces Python backend completely with Supabase BaaS (Database + Auth)
// ====================================================================

// 1. CONFIGURATION:
// Replace these with your Supabase Project URL and Anon Key from:
// Supabase Dashboard -> Project Settings -> API
const SUPABASE_CONFIG = {
  url: localStorage.getItem("supabase_url") || "https://your-project-ref.supabase.co",
  anonKey: localStorage.getItem("supabase_anon_key") || "your-anon-key"
};

// Initialize Supabase Client
let supabaseClient = null;
if (window.supabase) {
  try {
    supabaseClient = window.supabase.createClient(SUPABASE_CONFIG.url, SUPABASE_CONFIG.anonKey);
  } catch (e) {
    console.warn("Supabase client initialized with fallback or placeholder:", e);
  }
}

// Helper to configure Supabase credentials dynamically
function setSupabaseConfig(url, anonKey) {
  if (url) localStorage.setItem("supabase_url", url);
  if (anonKey) localStorage.setItem("supabase_anon_key", anonKey);
  if (window.supabase) {
    supabaseClient = window.supabase.createClient(url, anonKey);
  }
}

// ====================================================================
// AUTHENTICATION SERVICES (Sign In, Sign Up, Sign Out, User Profile)
// ====================================================================

async function supabaseSignUp(name, email, phone, password) {
  if (!supabaseClient) throw new Error("Supabase client is not initialized. Please configure your Project URL and Anon Key.");
  
  const { data, error } = await supabaseClient.auth.signUp({
    email: email,
    password: password,
    options: {
      data: {
        name: name,
        phone: phone
      }
    }
  });

  if (error) throw error;
  return data;
}

async function supabaseSignIn(email, password) {
  if (!supabaseClient) throw new Error("Supabase client is not initialized. Please configure your Project URL and Anon Key.");

  const { data, error } = await supabaseClient.auth.signInWithPassword({
    email: email,
    password: password
  });

  if (error) throw error;
  return data;
}

async function supabaseSignOut() {
  if (supabaseClient) {
    await supabaseClient.auth.signOut();
  }
  localStorage.removeItem("token");
  localStorage.removeItem("userName");
  window.location.href = "login.html";
}

async function supabaseGetSession() {
  if (!supabaseClient) return null;
  const { data: { session }, error } = await supabaseClient.auth.getSession();
  if (error || !session) return null;
  return session;
}

async function supabaseGetProfile(userId) {
  if (!supabaseClient) return null;
  const { data, error } = await supabaseClient
    .from("profiles")
    .select("*")
    .eq("id", userId)
    .single();

  if (error) {
    console.warn("Could not fetch profile from Supabase:", error);
    return null;
  }
  return data;
}

async function supabaseUpdateProfile(userId, updates) {
  if (!supabaseClient) return;
  const { data, error } = await supabaseClient
    .from("profiles")
    .update(updates)
    .eq("id", userId);

  if (error) throw error;
  return data;
}

// ====================================================================
// METERS / CONNECTIONS SERVICES
// ====================================================================

async function supabaseGetMeters(userId) {
  if (!supabaseClient) return [];
  const { data, error } = await supabaseClient
    .from("meters")
    .select("*")
    .eq("user_id", userId)
    .order("created_at", { ascending: false });

  if (error) throw error;
  return data || [];
}

async function supabaseAddMeter(userId, meter) {
  if (!supabaseClient) return;
  const { data, error } = await supabaseClient
    .from("meters")
    .insert([{
      user_id: userId,
      service_number: meter.service_number,
      board_name: meter.board_name,
      consumer_name: meter.consumer_name,
      address: meter.address || "Main Residential Premise"
    }])
    .select();

  if (error) throw error;
  return data ? data[0] : null;
}

async function supabaseDeleteMeter(meterId) {
  if (!supabaseClient) return;
  const { error } = await supabaseClient
    .from("meters")
    .delete()
    .eq("id", meterId);

  if (error) throw error;
}

// ====================================================================
// BILLS SERVICES
// ====================================================================

async function supabaseGetBills(userId) {
  if (!supabaseClient) return [];
  const { data, error } = await supabaseClient
    .from("bills")
    .select("*")
    .eq("user_id", userId)
    .order("created_at", { ascending: false });

  if (error) throw error;
  return data || [];
}

async function supabasePayBill(billId) {
  if (!supabaseClient) return;
  const { data, error } = await supabaseClient
    .from("bills")
    .update({ status: "Paid" })
    .eq("id", billId)
    .select();

  if (error) throw error;
  return data ? data[0] : null;
}

// ====================================================================
// REMINDERS & NOTIFICATIONS SERVICES
// ====================================================================

async function supabaseGetReminders(userId) {
  if (!supabaseClient) return [];
  const { data, error } = await supabaseClient
    .from("reminders")
    .select("*")
    .eq("user_id", userId);

  if (error) throw error;
  return data || [];
}

async function supabaseToggleReminder(reminderId, enabled) {
  if (!supabaseClient) return;
  const { error } = await supabaseClient
    .from("reminders")
    .update({ enabled: enabled })
    .eq("id", reminderId);

  if (error) throw error;
}

async function supabaseGetNotifications(userId) {
  if (!supabaseClient) return [];
  const { data, error } = await supabaseClient
    .from("notifications")
    .select("*")
    .eq("user_id", userId)
    .order("created_at", { ascending: false });

  if (error) throw error;
  return data || [];
}
