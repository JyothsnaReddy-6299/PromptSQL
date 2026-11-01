import { useEffect, useState } from "react";
import { relationshipAPI } from "../services/api";

type KeyPair = { left: string; right: string };
type Dataset = { id: string; name: string; table_name: string; revision: number; columns: { name: string; type: string }[] };
type SideProfile = { total_records: number; incomplete_key_records: number; complete_key_records: number; distinct_complete_keys: number; duplicate_key_groups: number; excess_duplicate_records: number; maximum_key_frequency: number; matched_source_records: number; unmatched_source_records: number };
type Profile = { left: SideProfile; right: SideProfile; cardinality: string; expected_inner_join_records: number; expected_join_records: number; expansion_per_left_record: number; semantics: string; measured_at: string };
type Relationship = { id: string; name: string; left_dataset_id: string; right_dataset_id: string; keys: KeyPair[]; join_type: "INNER" | "LEFT"; active: boolean; approved: boolean; needs_revalidation: boolean; profile: Profile };
const measures: [keyof SideProfile, string][] = [
  ["total_records", "Total source records"], ["complete_key_records", "Records with complete keys"],
  ["incomplete_key_records", "Records with any NULL key part"], ["distinct_complete_keys", "Distinct complete keys"],
  ["duplicate_key_groups", "Keys occurring more than once"], ["excess_duplicate_records", "Records beyond first per key"],
  ["matched_source_records", "Source records with a counterpart"], ["unmatched_source_records", "Source records without a counterpart"],
];
function ProfileView({ profile, left, right }: { profile: Profile; left: string; right: string }) {
  return <div className="space-y-3">
    <div className="overflow-x-auto"><table className="w-full text-sm border-collapse"><caption className="text-left font-semibold mb-2">Measured key quality</caption>
      <thead><tr className="bg-[#F7F2EC]"><th className="p-2 text-left">Measure</th><th className="p-2 text-right">Left: {left}</th><th className="p-2 text-right">Right: {right}</th></tr></thead>
      <tbody>{measures.map(([key, label]) => <tr key={key} className="border-b border-[#E8DED3]"><th className="p-2 text-left font-normal">{label}</th><td className="p-2 text-right">{profile.left[key].toLocaleString()}</td><td className="p-2 text-right">{profile.right[key].toLocaleString()}</td></tr>)}</tbody>
    </table></div>
    <p><strong>{profile.cardinality}</strong> · Expected INNER records: {profile.expected_inner_join_records.toLocaleString()} · Expected selected join records: {profile.expected_join_records.toLocaleString()} · Expansion per left source record: {profile.expansion_per_left_record.toFixed(3)}×</p>
    <p className="text-xs text-[#6F6A67]">{profile.semantics}</p>
  </div>;
}
export default function RelationshipsManager() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [relationships, setRelationships] = useState<Relationship[]>([]);
  const [left, setLeft] = useState(""); const [right, setRight] = useState("");
  const [name, setName] = useState(""); const [joinType, setJoinType] = useState<"INNER" | "LEFT">("INNER");
  const [keys, setKeys] = useState<KeyPair[]>([{ left: "", right: "" }]);
  const [editing, setEditing] = useState<string>();
  const [preview, setPreview] = useState<{ profile: Profile; preview_digest: string }>();
  const [approved, setApproved] = useState(false); const [busy, setBusy] = useState(false);
  const [error, setError] = useState(""); const [notice, setNotice] = useState("");
  const [suggestions, setSuggestions] = useState<{ keys: KeyPair[]; profile: Profile; reason: string }[]>([]);
  const [view, setView] = useState<"connections" | "list">("connections");
  const [inspecting, setInspecting] = useState<string>();
  async function load() {
    const ds = await relationshipAPI.datasets(); setDatasets(ds.datasets);
    const result = await relationshipAPI.list(); setRelationships(result.relationships);
  }
  useEffect(() => { load().catch(e => setError(e.message)); }, []);
  useEffect(() => { setPreview(undefined); setApproved(false); setSuggestions([]); }, [left, right, keys, joinType]);
  const l = datasets.find(d => d.id === left); const r = datasets.find(d => d.id === right);
  const label = (id: string) => datasets.find(d => d.id === id)?.name || "Unavailable dataset";
  const inputClass = "w-full rounded-lg border border-[#D8CCC1] bg-white px-3 py-2 text-sm text-[#241C20]";
  const buttonClass = "rounded-lg bg-[#5A2F59] text-white px-4 py-2 text-sm font-semibold disabled:opacity-50";
  function reset() { setEditing(undefined); setLeft(""); setRight(""); setName(""); setKeys([{ left: "", right: "" }]); setPreview(undefined); setApproved(false); }
  async function run(action: () => Promise<void>) { setBusy(true); setError(""); setNotice(""); try { await action(); } catch(e) { setError(e instanceof Error ? e.message : "Request failed"); } finally { setBusy(false); } }
  const body = { name, left_dataset_id: left, right_dataset_id: right, keys, join_type: joinType, approved, active: true, preview_digest: preview?.preview_digest || "" };
  return <section className="bg-[#FFFDFC] text-[#241C20] border border-[#E8DED3] rounded-2xl p-6 space-y-6" aria-label="Relationships workspace">
    <header><h1 className="text-xl font-bold">Dataset relationships</h1><p className="text-sm text-[#6F6A67] mt-1">Measure and approve how datasets connect before asking questions across them. These are analytical relationships, not verified database foreign keys.</p></header>
    {error && <p role="alert" className="rounded-lg bg-red-50 text-red-800 p-3">{error}</p>}
    {notice && <p role="status" className="rounded-lg bg-emerald-50 text-emerald-800 p-3">{notice}</p>}
    <div className="flex gap-2" role="group" aria-label="Relationship view"><button className={buttonClass} aria-pressed={view === "connections"} onClick={() => setView("connections")}>Connections</button><button className={buttonClass} aria-pressed={view === "list"} onClick={() => setView("list")}>Accessible list</button></div>
    {view === "connections" && <div className="overflow-auto rounded-xl bg-[#F7F2EC] border border-[#E8DED3] p-4">
      <svg viewBox={`0 0 760 ${Math.max(160, relationships.length * 96)}`} className="w-full min-w-[560px]" role="img" aria-label="Approved dataset connections; equivalent details appear in the relationship list below">
        {relationships.length === 0 && <text x="30" y="65" fill="#6F6A67">No connections yet. Create your first relationship below.</text>}
        {relationships.map((rel, i) => <g key={rel.id} opacity={rel.active && !rel.needs_revalidation ? 1 : 0.5}>
          <rect x="10" y={i*96+12} width="220" height="58" rx="10" fill="white" stroke="#D8CCC1"/><text x="22" y={i*96+45} fontSize="13" fill="#241C20">{label(rel.left_dataset_id).slice(0,27)}</text>
          <line x1="230" y1={i*96+40} x2="530" y2={i*96+40} stroke="#5A2F59" strokeWidth="2" strokeDasharray={rel.needs_revalidation ? "5 4" : undefined}/>
          <text x="250" y={i*96+30} fontSize="11" fill="#5A2F59">{rel.name.slice(0,32)} · {rel.join_type}</text><text x="250" y={i*96+60} fontSize="10" fill="#6F6A67">{rel.profile.cardinality}</text>
          <rect x="530" y={i*96+12} width="220" height="58" rx="10" fill="white" stroke="#D8CCC1"/><text x="542" y={i*96+45} fontSize="13" fill="#241C20">{label(rel.right_dataset_id).slice(0,27)}</text>
        </g>)}
      </svg></div>}
    <ul className="space-y-3" aria-label="Saved relationships">{relationships.map(rel => <li key={rel.id} className="border border-[#E8DED3] rounded-xl p-4 space-y-2">
      <div className="flex flex-wrap justify-between gap-3"><div><h2 className="font-bold">{rel.name}</h2><p className="text-sm">{label(rel.left_dataset_id)} → {label(rel.right_dataset_id)} · {rel.join_type} · {rel.profile.cardinality}</p><p className="text-xs text-[#6F6A67]">{rel.keys.map(k => `${k.left} = ${k.right}`).join(" AND ")}</p><p className={`text-xs font-bold ${rel.needs_revalidation ? "text-amber-800" : "text-[#5A2F59]"}`}>{rel.needs_revalidation ? "Requires revalidation" : !rel.active ? "Inactive" : "Approved and active"}</p></div>
      <div className="flex flex-wrap gap-2 items-start"><button className={buttonClass} onClick={() => setInspecting(inspecting === rel.id ? undefined : rel.id)}>Inspect</button><button className={buttonClass} onClick={() => { setEditing(rel.id); setLeft(rel.left_dataset_id); setRight(rel.right_dataset_id); setName(rel.name); setKeys(rel.keys); setJoinType(rel.join_type); setPreview(undefined); setApproved(false); }}>Edit / revalidate</button><button className={buttonClass} disabled={busy || !rel.active} onClick={() => run(async () => { await relationshipAPI.deactivate(rel.id); await load(); })}>Deactivate</button></div></div>
      {inspecting === rel.id && <><p className="text-xs">Saved approval profile, measured {rel.profile.measured_at}. Revalidate to inspect current data.</p><ProfileView profile={rel.profile} left={label(rel.left_dataset_id)} right={label(rel.right_dataset_id)}/></>}
    </li>)}</ul>
    <form className="border-t border-[#E8DED3] pt-5 space-y-4" onSubmit={e => { e.preventDefault(); run(async () => { setPreview(await relationshipAPI.preview(body)); }); }}>
      <div className="flex justify-between"><h2 className="font-bold text-lg">{editing ? "Edit and revalidate relationship" : "Create a relationship"}</h2><button type="button" onClick={reset} className="text-sm underline">Reset</button></div>
      <label className="block text-sm">Relationship meaning / name<input className={inputClass} value={name} onChange={e => setName(e.target.value)} maxLength={150} placeholder="Orders contain order items" required/></label>
      <div className="grid md:grid-cols-2 gap-4">{(["left", "right"] as const).map(side => <div key={side}><label className="block text-sm">{side === "left" ? "Left dataset (preserved by LEFT join)" : "Right dataset"}<select className={inputClass} value={side === "left" ? left : right} required onChange={e => { (side === "left" ? setLeft : setRight)(e.target.value); setKeys([{ left: "", right: "" }]); }}><option value="">Select a dataset</option>{datasets.filter(d => d.id !== (side === "left" ? right : left)).map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label><ul className="text-xs mt-2 max-h-32 overflow-y-auto" aria-label={`${side} dataset schema`}>{(side === "left" ? l : r)?.columns.map(c => <li key={c.name}>{c.name} <span className="text-[#6F6A67]">{c.type}</span></li>)}</ul></div>)}</div>
      {keys.map((key, i) => <div className="flex gap-3 items-end" key={i}>{(["left", "right"] as const).map(side => <label className="flex-1 text-sm" key={side}>{side} key {i+1}<select className={inputClass} value={key[side]} required onChange={e => setKeys(keys.map((k,j) => j === i ? { ...k, [side]: e.target.value } : k))}><option value="">Select column</option>{(side === "left" ? l : r)?.columns.map(c => <option key={c.name} value={c.name}>{c.name} ({c.type})</option>)}</select></label>)}<button type="button" disabled={keys.length === 1} onClick={() => setKeys(keys.filter((_,j) => j !== i))} className="p-2 text-sm underline" aria-label={`Remove key ${i+1}`}>Remove</button></div>)}
      <div className="flex gap-3 flex-wrap"><button type="button" className={buttonClass} disabled={keys.length >= 8} onClick={() => setKeys([...keys, { left: "", right: "" }])}>Add composite key part</button><button type="button" className={buttonClass} disabled={busy || !left || !right} onClick={() => run(async () => { const data = await relationshipAPI.suggest(left,right); setSuggestions(data.suggestions); if (!data.suggestions.length) setNotice("No same-name compatible key candidates. Select keys manually."); })}>Suggest measured keys</button><label className="text-sm">Join type<select className={inputClass} value={joinType} onChange={e => setJoinType(e.target.value as "INNER" | "LEFT")}><option>INNER</option><option>LEFT</option></select></label></div>
      {suggestions.map((s,i) => <div className="bg-[#F7F2EC] rounded-lg p-3 text-sm" key={i}><p>{s.keys.map(k => `${k.left} = ${k.right}`).join(" AND ")} · {s.profile.cardinality} · {s.profile.expected_join_records} INNER records</p><p className="text-xs">{s.reason}</p><button type="button" className="underline mt-2" onClick={() => setKeys(s.keys)}>Use candidate and inspect</button></div>)}
      <button className={buttonClass} disabled={busy}>{busy ? "Measuring…" : "Preview relationship"}</button>
      {preview && <div className="border border-[#E8DED3] rounded-xl p-4 space-y-4"><ProfileView profile={preview.profile} left={l?.name || "Left"} right={r?.name || "Right"}/><label className="flex gap-2 text-sm"><input type="checkbox" checked={approved} onChange={e => setApproved(e.target.checked)}/>I inspected these keys, join direction and measured counts, and approve this analytical relationship.</label><button type="button" className={buttonClass} disabled={busy || !approved} onClick={() => run(async () => { await relationshipAPI.save(body, editing); await load(); reset(); setNotice("Relationship approved. Ask AI about these datasets by name."); })}>Confirm and save approval</button></div>}
    </form>
    <p className="text-xs text-[#6F6A67]">Freshness uses schema fingerprints and application mutation revisions. Immutable dataset versions are not available. Changes through PromptSQL require revalidation; external writes must be revalidated manually.</p>
  </section>;
}
