import json, subprocess, sys
from xml.sax.saxutils import escape
JS = r'''const fs=require("fs");function jcs(v){if(Array.isArray(v))return "["+v.map(jcs).join(",")+"]";
if(v&&typeof v==="object")return "{"+Object.keys(v).sort().map(k=>JSON.stringify(k)+":"+jcs(v[k])).join(",")+"}";
return JSON.stringify(v);}process.stdout.write(jcs(JSON.parse(fs.readFileSync(0,"utf8"))));'''
def jcs(o): return subprocess.run(["node", "-e", JS], input=json.dumps(o).encode(), capture_output=True, check=True).stdout.decode()
def cs(tag, text, ind): return f'{ind}<{tag}><gco:CharacterString>{escape(text)}</gco:CharacterString></{tag}>'
def ident(i, ind): return (f'{ind}<cit:identifier><mcc:MD_Identifier><mcc:code><gco:CharacterString>{escape(i["code"])}</gco:CharacterString></mcc:code>'
                          f'<mcc:codeSpace><gco:CharacterString>{escape(i["codeSpace"])}</gco:CharacterString></mcc:codeSpace></mcc:MD_Identifier></cit:identifier>')
def citation(c, ind):  # CI_Citation in schema order: title, edition, identifier*
    out = [f'{ind}<cit:CI_Citation>', cs("cit:title", c["title"], ind + "  ")]
    if "edition" in c: out.append(cs("cit:edition", c["edition"], ind + "  "))
    out += [ident(i, ind + "  ") for i in c.get("identifier", [])]
    return out + [f'{ind}</cit:CI_Citation>']
def step(s, I="  "):
    o = [f'{I}<mrl:processStep><mrl:LE_ProcessStep id="{s["id"]}">', cs("mrl:description", s["description"], I + "  ")]
    o += [f'{I}  <mrl:source xlink:href="#{r}"/>' for r in s["source"]]          # LI_ProcessStep part
    p = s["processingInformation"]; J = I + "    "
    o.append(f'{I}  <mrl:processingInformation><mrl:LE_Processing>')
    for a in p["algorithm"]:                                                     # algorithm* first
        if isinstance(a, str): o.append(f'{J}<mrl:algorithm xlink:href="#{a}"/>'); continue
        o += [f'{J}<mrl:algorithm><mrl:LE_Algorithm id="{a["id"]}">', f'{J}  <mrl:citation>']
        o += citation(a["citation"], J + "    ")
        o += [f'{J}  </mrl:citation>', cs("mrl:description", a["description"], J + "  "), f'{J}</mrl:LE_Algorithm></mrl:algorithm>']
    i = p["identifier"]
    o.append(f'{J}<mrl:identifier><mcc:MD_Identifier><mcc:code><gco:CharacterString>{i["code"]}</gco:CharacterString></mcc:code>'
             f'<mcc:codeSpace><gco:CharacterString>{i["codeSpace"]}</gco:CharacterString></mcc:codeSpace></mcc:MD_Identifier></mrl:identifier>')
    o.append(f'{J}<mrl:softwareReference xlink:href="#{p["softwareReference"]}"/>')
    o.append(cs("mrl:runTimeParameters", jcs(p["runTimeParameters"]), J))
    o.append(f'{I}  </mrl:LE_Processing></mrl:processingInformation>')
    for r in s.get("report", []):                                                # then report*
        o += [f'{I}  <mrl:report><mrl:LE_ProcessStepReport>', cs("mrl:name", r["name"], I + "    "),
              cs("mrl:description", jcs(r["description"]), I + "    "), f'{I}  </mrl:LE_ProcessStepReport></mrl:report>']
    o += [f'{I}  <mrl:output><mrl:LE_Source id="{x["id"]}"/></mrl:output>' for x in s["output"]]   # then output*
    return o + [f'{I}</mrl:LE_ProcessStep></mrl:processStep>']
NS = ('<mrl:LI_Lineage xmlns:mrl="http://standards.iso.org/iso/19115/-3/mrl/2.0"\n'
      '    xmlns:mcc="http://standards.iso.org/iso/19115/-3/mcc/1.0" xmlns:cit="http://standards.iso.org/iso/19115/-3/cit/2.0"\n'
      '    xmlns:gco="http://standards.iso.org/iso/19115/-3/gco/1.0" xmlns:xlink="http://www.w3.org/1999/xlink">')
print("\n".join([NS] + step(json.load(open(sys.argv[1]))) + ["</mrl:LI_Lineage>"]))
