import { getStore } from "@netlify/blobs";

// Write-only. Step 1 (the reviewer's own answer) can be saved and changed until the tool's answer has been revealed
// for that item; after the reveal it is locked. Step 2 (agreement with the tool) can be saved only after the reveal.
// Only the codes listed in REVIEWERS are accepted; nothing can be read back through this function.
const STORE = "d5-expert-review";
const REVIEWERS = __REVIEWERS__;
const ANSWERS = ["violation", "no_violation", "cannot_tell"];
const AGREE = ["agree", "disagree", "partly"];
const text = (v, n) => (typeof v === "string" ? v.slice(0, n) : "");
// once per link, on the start page: consent and the labeller's experience (for the paper's description of the labellers)
const PROFILE = {
  role: ["bachelor", "master", "phd_researcher", "practitioner", "other"],
  time: ["lt6m", "6to12m", "1to3y", "gt3y"],
  assistive_tech: ["never", "tried", "regular"],  // screen readers, magnifiers, voice control ...
};
const AREAS = ["web", "documents", "other", "none"];
const STANDARDS = ["wcag", "pdfua", "other", "none"];

export default async (req) => {
  if (req.method !== "POST") return new Response("Use POST", { status: 405 });
  let body;
  try { body = await req.json(); } catch { return new Response("Not JSON", { status: 400 }); }
  const reviewer = String(body.reviewer || "");
  if (!REVIEWERS.includes(reviewer)) return new Response("Unknown reviewer link", { status: 400 });
  const store = getStore({ name: STORE, consistency: "strong" });
  if (body.step === "profile") {
    if (body.consent !== true) return new Response("Consent is needed", { status: 400 });
    const p = body.profile || {}, profile = {};
    for (const [k, allowed] of Object.entries(PROFILE)) {
      if (!allowed.includes(p[k])) return new Response(`Unknown ${k}`, { status: 400 });
      profile[k] = p[k];
    }
    const areas = Array.isArray(p.areas) ? p.areas.filter((a) => AREAS.includes(a)) : [];
    if (!areas.length) return new Response("Unknown areas", { status: 400 });
    profile.areas = [...new Set(areas)];
    if (profile.role === "other") profile.role_other = text(p.role_other, 200);  // what "Other" means, in their words
    if (profile.areas.includes("other")) profile.areas_other = text(p.areas_other, 200);
    const standards = Array.isArray(p.standards) ? p.standards.filter((a) => STANDARDS.includes(a)) : [];
    if (!standards.length) return new Response("Unknown standards", { status: 400 });
    profile.standards = [...new Set(standards)];
    if (profile.standards.includes("other")) profile.standards_other = text(p.standards_other, 200);
    const key = `${reviewer}/_profile`;
    const old = await store.get(key, { type: "json" });
    await store.setJSON(key, { reviewer, consent: true, consent_at: new Date().toISOString(), profile,
                               history: old ? [...(old.history || []), { profile: old.profile, consent_at: old.consent_at }] : [] });
    return Response.json({ ok: true });
  }
  const item = String(body.item || "");
  if (!/^D5-\d{3}$/.test(item)) return new Response("Unknown item", { status: 400 });
  const key = `${reviewer}/${item}`;
  const record = (await store.get(key, { type: "json" })) || { reviewer, item, history: [] };
  const now = new Date().toISOString();
  if (body.step === 2) {
    if (!record.revealed_at) return new Response("Answer step 1 first", { status: 409 });
    if (!AGREE.includes(body.agree)) return new Response("Unknown agreement", { status: 400 });
    record.agree = body.agree;
    record.agree_comment = text(body.comment, 2000);
    record.agree_saved_at = now;
  } else {
    if (record.revealed_at) return new Response("Your first answer is locked after the tool's answer was shown", { status: 409 });
    if (!ANSWERS.includes(body.answer)) return new Response("Unknown answer", { status: 400 });
    if (record.answer) record.history.push({ answer: record.answer, reason: record.reason, saved_at: record.saved_at });
    record.answer = body.answer;
    record.reason = text(body.reason, 2000);
    record.seconds = Number.isFinite(body.seconds) ? Math.max(0, Math.min(36000, Math.round(body.seconds))) : null;
    record.saved_at = now;
  }
  await store.setJSON(key, record);
  return Response.json({ ok: true });
};

export const config = { path: "/api/save" };
