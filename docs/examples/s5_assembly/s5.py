"""Assemble .prov records into one JSON Lines file, verify it, export one ISO LI_Lineage."""
import hashlib, json, subprocess, sys
from xml.sax.saxutils import escape, quoteattr
JS = r'''const fs=require("fs");function jcs(v){if(Array.isArray(v))return "["+v.map(jcs).join(",")+"]";
if(v&&typeof v==="object")return "{"+Object.keys(v).sort().map(k=>JSON.stringify(k)+":"+jcs(v[k])).join(",")+"}";
return JSON.stringify(v);}process.stdout.write(jcs(JSON.parse(fs.readFileSync(0,"utf8"))));'''
def jcs_bytes(obj): return subprocess.run(["node", "-e", JS], input=json.dumps(obj).encode(), capture_output=True, check=True).stdout
def sha(b): return hashlib.sha256(b).hexdigest()

def assemble(record_paths):
    lines = sorted(open(p, "rb").read() for p in record_paths)
    lines = sorted(set(lines), key=sha)
    return b"".join(l + b"\n" for l in lines)

def citations(rec):            # (dataset sha256, cited record sha256) per source
    for s in rec.get("source", []):
        for m in s.get("sourceMetadata", []):
            if "sha256" in m:
                yield s, s.get("sourceCitation", {}).get("sha256"), m["sha256"]

def outputs(rec):              # dataset sha256 -> producing step id
    return {o["sourceCitation"]["sha256"]: st["id"] for st in rec["processStep"]
            for o in st.get("output", []) if "sha256" in o.get("sourceCitation", {})}

def verify(blob):
    problems, members = [], {}
    raw = blob.split(b"\n")
    if raw[-1] != b"": problems.append("last line lacks LF")
    for line in raw[:-1]:
        rec = json.loads(line)
        if jcs_bytes(rec) != line: problems.append(f"line {sha(line)[:12]} is not canonical")
        members[sha(line)] = rec
    order = [sha(l) for l in raw[:-1]]
    if order != sorted(set(order)): problems.append("lines not sorted by sha256 / duplicates")
    cited, gaps = set(), []
    for h, rec in members.items():
        for src, data_h, rec_h in citations(rec):
            cited.add(rec_h)
            if rec_h not in members: gaps.append((h[:12], src["id"], rec_h)); continue
            if data_h not in outputs(members[rec_h]):
                problems.append(f"{h[:12]}:{src['id']} reads {data_h[:12]}, which record {rec_h[:12]} did not output")
    sinks = [h for h in members if h not in cited]
    if len(sinks) != 1: problems.append(f"{len(sinks)} sinks")
    return members, sinks, gaps, problems

# ---------- ISO export ----------
CSv = lambda tag, text, ind: f'{ind}<{tag}><gco:CharacterString>{escape(str(text))}</gco:CharacterString></{tag}>'
def ident(code, space, ind):
    return (f'{ind}<cit:identifier><mcc:MD_Identifier><mcc:code><gco:CharacterString>{escape(code)}</gco:CharacterString></mcc:code>'
            f'<mcc:codeSpace><gco:CharacterString>{escape(space)}</gco:CharacterString></mcc:codeSpace></mcc:MD_Identifier></cit:identifier>')
def citation(c, ind, pid=None):
    head = f'{ind}<cit:CI_Citation id="{pid(c["id"])}">' if pid and "id" in c else f'{ind}<cit:CI_Citation>'
    o = [head, CSv("cit:title", c["title"], ind + "  ")]
    if "edition" in c: o.append(CSv("cit:edition", c["edition"], ind + "  "))
    o += [ident(i["code"], i["codeSpace"], ind + "  ") for i in c.get("identifier", [])]
    if "sha256" in c: o.append(ident(c["sha256"], "sha256", ind + "  "))
    o += [CSv("cit:otherCitationDetails", d, ind + "  ") for d in c.get("otherCitationDetails", [])]
    o += [f'{ind}  <cit:onlineResource><cit:CI_OnlineResource><cit:linkage><gco:CharacterString>{escape(r["linkage"])}</gco:CharacterString></cit:linkage></cit:CI_OnlineResource></cit:onlineResource>'
          for r in c.get("onlineResource", [])]
    return o + [f'{ind}</cit:CI_Citation>']
def prop_cit(tag, c, ind, pid):
    if isinstance(c, str): return [f'{ind}<{tag} xlink:href="#{pid(c)}"/>']
    return [f'{ind}<{tag}>'] + citation(c, ind + "  ", pid) + [f'{ind}</{tag}>']

def export(members, sinks, assembly_hash, assembly_title):
    # ancestors first: a member comes after every member it cites; ties by hash
    order, placed = [], set()
    while len(order) < len(members):
        ready = sorted(h for h, r in members.items() if h not in placed
                       and all(rh in placed or rh not in members for _s, _d, rh in citations(r)))
        order.append(ready[0]); placed.add(ready[0])
    I = "  "
    o = ['<mrl:LI_Lineage xmlns:mrl="http://standards.iso.org/iso/19115/-3/mrl/2.0"',
         '    xmlns:mcc="http://standards.iso.org/iso/19115/-3/mcc/1.0" xmlns:cit="http://standards.iso.org/iso/19115/-3/cit/2.0"',
         '    xmlns:gco="http://standards.iso.org/iso/19115/-3/gco/1.0" xmlns:gml="http://www.opengis.net/gml/3.2"',
         '    xmlns:xlink="http://www.w3.org/1999/xlink">']
    o.append(CSv("mrl:statement", members[sinks[0]]["statement"], I))
    o += [f'{I}<mrl:additionalDocumentation>'] + citation({"title": assembly_title, "sha256": assembly_hash}, I + "  ") + [f'{I}</mrl:additionalDocumentation>']
    for h in order:                                         # sources
        rec, pid = members[h], (lambda local, h=h: f"r{h[:12]}.{local}")
        for s in rec.get("source", []):
            o.append(f'{I}<mrl:source><mrl:LI_Source id="{pid(s["id"])}">')
            if "description" in s: o.append(CSv("mrl:description", s["description"], I + "  "))
            if "sourceCitation" in s: o += [f'{I}  <mrl:sourceCitation>'] + citation(s["sourceCitation"], I + "    ") + [f'{I}  </mrl:sourceCitation>']
            for m in s.get("sourceMetadata", []):
                o += [f'{I}  <mrl:sourceMetadata>'] + citation(m, I + "    ") + [f'{I}  </mrl:sourceMetadata>']
            for _s, data_h, rec_h in citations({"source": [s]}):      # the link the assembly adds
                if rec_h in members:
                    o.append(f'{I}  <mrl:sourceStep xlink:href="#r{rec_h[:12]}.{outputs(members[rec_h])[data_h]}"/>')
            o.append(f'{I}</mrl:LI_Source></mrl:source>')
    for h in order:                                         # steps
        rec, pid = members[h], (lambda local, h=h: f"r{h[:12]}.{local}")
        for st in rec["processStep"]:
            o.append(f'{I}<mrl:processStep><mrl:LE_ProcessStep id="{pid(st["id"])}">')
            o.append(CSv("mrl:description", st["description"], I + "  "))
            if "stepDateTime" in st:
                o.append(f'{I}  <mrl:stepDateTime><gml:TimeInstant gml:id="{pid(st["id"])}.t"><gml:timePosition>{st["stepDateTime"]}</gml:timePosition></gml:TimeInstant></mrl:stepDateTime>')
            o += [f'{I}  <mrl:source xlink:href="#{pid(r)}"/>' for r in st.get("source", [])]
            p, J = st["processingInformation"], I + "    "
            o.append(f'{I}  <mrl:processingInformation><mrl:LE_Processing>')
            for a in p.get("algorithm", []):
                if isinstance(a, str): o.append(f'{J}<mrl:algorithm xlink:href="#{pid(a)}"/>'); continue
                o += [f'{J}<mrl:algorithm><mrl:LE_Algorithm id="{pid(a["id"])}">', f'{J}  <mrl:citation>'] + citation(a["citation"], J + "    ") + \
                     [f'{J}  </mrl:citation>', CSv("mrl:description", a["description"], J + "  "), f'{J}</mrl:LE_Algorithm></mrl:algorithm>']
            i = p["identifier"]
            o.append(f'{J}<mrl:identifier><mcc:MD_Identifier><mcc:code><gco:CharacterString>{escape(i["code"])}</gco:CharacterString></mcc:code>'
                     f'<mcc:codeSpace><gco:CharacterString>{escape(i["codeSpace"])}</gco:CharacterString></mcc:codeSpace></mcc:MD_Identifier></mrl:identifier>')
            o += prop_cit("mrl:softwareReference", p["softwareReference"], J, pid)
            o.append(CSv("mrl:runTimeParameters", jcs_bytes(p["runTimeParameters"]).decode(), J))
            o.append(f'{I}  </mrl:LE_Processing></mrl:processingInformation>')
            for r in st.get("report", []):
                o += [f'{I}  <mrl:report><mrl:LE_ProcessStepReport>', CSv("mrl:name", r["name"], I + "    "),
                      CSv("mrl:description", jcs_bytes(r["description"]).decode(), I + "    "), f'{I}  </mrl:LE_ProcessStepReport></mrl:report>']
            for out in st.get("output", []):
                if "sourceCitation" in out:
                    o += [f'{I}  <mrl:output><mrl:LE_Source id="{pid(out["id"])}"><mrl:sourceCitation>'] + citation(out["sourceCitation"], I + "    ") + \
                         [f'{I}  </mrl:sourceCitation></mrl:LE_Source></mrl:output>']
                else:
                    o.append(f'{I}  <mrl:output><mrl:LE_Source id="{pid(out["id"])}"/></mrl:output>')
            o.append(f'{I}</mrl:LE_ProcessStep></mrl:processStep>')
    return "\n".join(o + ["</mrl:LI_Lineage>"])

if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "canon":                  # canon in.json out.prov [PARENT_HASH=...]
        text = open(sys.argv[2]).read()
        for kv in sys.argv[4:]:
            k, v = kv.split("="); text = text.replace(k, v)
        b = jcs_bytes(json.loads(text)); assert b"\n" not in b
        open(sys.argv[3], "wb").write(b); print(sys.argv[3], sha(b))
    elif cmd == "assemble":             # assemble out.jsonl a.prov b.prov ...
        blob = assemble(sys.argv[3:]); open(sys.argv[2], "wb").write(blob); print(sys.argv[2], sha(blob))
    elif cmd == "verify":
        blob = open(sys.argv[2], "rb").read()
        members, sinks, gaps, problems = verify(blob)
        print("members:", [h[:12] for h in members], "| sink:", [h[:12] for h in sinks])
        print("unresolved citations (missing ancestors):", [(c, s, r[:12]) for c, s, r in gaps] or "none")
        print("VERIFIED" if not problems else "FAILED: " + "; ".join(problems))
    elif cmd == "export":               # export assembly.jsonl title
        blob = open(sys.argv[2], "rb").read()
        members, sinks, gaps, problems = verify(blob)
        assert not problems, problems
        print(export(members, sinks, sha(blob), sys.argv[3]))
