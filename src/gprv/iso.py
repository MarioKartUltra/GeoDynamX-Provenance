"""ISO 19115-3 lineage export (spec §10): one flat mrl:LI_Lineage per assembly, elements in schema order."""
from xml.sax.saxutils import escape

from .assembly import citations, producers, verify
from .canon import canonical, sha256

NAMESPACES = [
    '<mrl:LI_Lineage xmlns:mrl="http://standards.iso.org/iso/19115/-3/mrl/2.0"',
    '    xmlns:mcc="http://standards.iso.org/iso/19115/-3/mcc/1.0" xmlns:cit="http://standards.iso.org/iso/19115/-3/cit/2.0"',
    '    xmlns:gco="http://standards.iso.org/iso/19115/-3/gco/1.0" xmlns:gml="http://www.opengis.net/gml/3.2"',
    '    xmlns:xlink="http://www.w3.org/1999/xlink">',
]
SCOPE_CODELIST = "https://standards.iso.org/iso/19115/resources/Codelists/cat/codelists.xml#MD_ScopeCode"


def export(blob: bytes, title: str, documented: str | None = None) -> str:
    """The ISO lineage XML of an assembly. ``additionalDocumentation`` cites ``title`` with the assembly's hash, or
    with ``documented`` when the exported file is a single record. Refuses an assembly that does not verify."""
    v = verify(blob)
    if not v.ok:
        raise ValueError("assembly does not verify: " + "; ".join(v.problems))
    return _Writer(v.members).lineage(v.sink, title, documented or sha256(blob))


def text(tag, value, ind):
    return f"{ind}<{tag}><gco:CharacterString>{escape(str(value))}</gco:CharacterString></{tag}>"


def json_text(value):
    return value if isinstance(value, str) else canonical(value).decode()


def md_identifier(i):
    space = f"<mcc:codeSpace><gco:CharacterString>{escape(i['codeSpace'])}</gco:CharacterString></mcc:codeSpace>" \
        if "codeSpace" in i else ""
    return f"<mcc:MD_Identifier><mcc:code><gco:CharacterString>{escape(i['code'])}</gco:CharacterString></mcc:code>{space}</mcc:MD_Identifier>"


class _Writer:
    def __init__(self, members):
        self.members, self.ids = members, set()

    def pid(self, member, local):
        """Export id: r + 12 hex of the member hash + . + local id, checked unique across the document."""
        x = f"r{member[:12]}.{local}"
        if x in self.ids:
            raise ValueError(f"exported id {x} is not unique")
        self.ids.add(x)
        return x

    def ref(self, member, local):
        return f"r{member[:12]}.{local}"

    def order(self):
        """Ancestors first: a member follows every member it cites; ties by hash."""
        order, placed = [], set()
        while len(order) < len(self.members):
            ready = sorted(h for h, r in self.members.items() if h not in placed
                           and all(p in placed or p not in self.members for _s, _d, p in citations(r)))
            order.append(ready[0])
            placed.add(ready[0])
        return order

    def citation(self, c, ind, member=None):
        head = f'{ind}<cit:CI_Citation id="{self.pid(member, c["id"])}">' if member and "id" in c else f"{ind}<cit:CI_Citation>"
        o = [head, text("cit:title", c["title"], ind + "  ")]
        if "edition" in c:
            o.append(text("cit:edition", c["edition"], ind + "  "))
        ids = list(c.get("identifier", [])) + ([{"code": c["sha256"], "codeSpace": "sha256"}] if "sha256" in c else [])
        o += [f"{ind}  <cit:identifier>{md_identifier(i)}</cit:identifier>" for i in ids]
        o += [text("cit:otherCitationDetails", d, ind + "  ") for d in c.get("otherCitationDetails", [])]
        o += [f"{ind}  <cit:onlineResource><cit:CI_OnlineResource><cit:linkage><gco:CharacterString>"
              f"{escape(r['linkage'])}</gco:CharacterString></cit:linkage></cit:CI_OnlineResource></cit:onlineResource>"
              for r in c.get("onlineResource", [])]
        return o + [f"{ind}</cit:CI_Citation>"]

    @staticmethod
    def origin_details(o) -> list:
        """A code origin as citation text (§10): its kind, its hash and what it covers, its licence."""
        h = o.get("contentHash", {})
        hashed = f"{h.get('algorithm', '')} {h['value']} ({h.get('covers', '')})" if "value" in h \
            else f"{h.get('algorithm', '')} ({h.get('covers', '')})"
        details = [f"kind {o.get('kind', '')}", hashed, f"license {o.get('license', '')}"]
        if o.get("citation"):
            details.append(o["citation"])
        if o.get("editable"):
            details.append("editable")
        return details

    def origin_citation(self, o) -> dict:
        """A step's code origin as a citation (§10): the software reference when the step cites no
        code base, else a documentation citation, since 19115-3 allows one software reference."""
        c = {"title": o.get("name", ""), "otherCitationDetails": self.origin_details(o),
             "onlineResource": [{"linkage": o.get("source", "")}]}
        if o.get("version") is not None:
            c["edition"] = o["version"]
        return c

    def wrapped(self, tag, c, ind, member):
        if isinstance(c, str):
            return [f'{ind}<{tag} xlink:href="#{self.ref(member, c)}"/>']
        return [f"{ind}<{tag}>"] + self.citation(c, ind + "  ", member) + [f"{ind}</{tag}>"]

    def lineage(self, sink, title, blob_hash):
        I, o = "  ", list(NAMESPACES)
        o.append(text("mrl:statement", self.members[sink]["statement"], I))
        o += [f"{I}<mrl:additionalDocumentation>"] + self.citation({"title": title, "sha256": blob_hash}, I + "  ") + \
             [f"{I}</mrl:additionalDocumentation>"]
        order = self.order()
        for h in order:
            for s in self.members[h].get("source", []):
                o += self.source(h, s, I)
        for h in order:
            for st in self.members[h]["processStep"]:
                o += self.step(h, st, I)
        return "\n".join(o + ["</mrl:LI_Lineage>"])

    def source(self, h, s, I):
        cls = "LE_Source" if "processedLevel" in s else "LI_Source"
        o = [f'{I}<mrl:source><mrl:{cls} id="{self.pid(h, s["id"])}">', text("mrl:description", s["description"], I + "  ")]
        if "sourceCitation" in s:
            o += self.wrapped("mrl:sourceCitation", s["sourceCitation"], I + "  ", h)
        for m in s.get("sourceMetadata", []):
            o += self.wrapped("mrl:sourceMetadata", m, I + "  ", h)
        if "scope" in s:
            lv = s["scope"]["level"]
            o.append(f'{I}  <mrl:scope><mcc:MD_Scope><mcc:level><mcc:MD_ScopeCode codeList="{SCOPE_CODELIST}" '
                     f'codeListValue="{lv}">{lv}</mcc:MD_ScopeCode></mcc:level></mcc:MD_Scope></mrl:scope>')
        for _src, dataset, parent in citations({"source": [s]}):        # the link the assembly adds
            if parent in self.members:
                o.append(f'{I}  <mrl:sourceStep xlink:href="#{self.ref(parent, producers(self.members[parent])[dataset])}"/>')
        if "processedLevel" in s:
            o.append(f"{I}  <mrl:processedLevel>{md_identifier(s['processedLevel'])}</mrl:processedLevel>")
        return o + [f"{I}</mrl:{cls}></mrl:source>"]

    def step(self, h, st, I):
        J = I + "    "
        o = [f'{I}<mrl:processStep><mrl:LE_ProcessStep id="{self.pid(h, st["id"])}">',
             text("mrl:description", st["description"], I + "  ")]
        if "stepDateTime" in st:
            o.append(f'{I}  <mrl:stepDateTime><gml:TimeInstant gml:id="{self.pid(h, st["id"] + ".t")}">'
                     f'<gml:timePosition>{st["stepDateTime"]}</gml:timePosition></gml:TimeInstant></mrl:stepDateTime>')
        for c in st.get("reference", []):
            o += self.wrapped("mrl:reference", c, I + "  ", h)
        o += [f'{I}  <mrl:source xlink:href="#{self.ref(h, r)}"/>' for r in st.get("source", [])]
        p = st.get("processingInformation")
        if p is not None:                                   # absent on a reported step
            o.append(f"{I}  <mrl:processingInformation><mrl:LE_Processing>")
            for a in p.get("algorithm", []):
                if isinstance(a, str):
                    o.append(f'{J}<mrl:algorithm xlink:href="#{self.ref(h, a)}"/>')
                    continue
                cit = a["citation"]
                if "codeOrigin" in a:                       # the origin rides the component's citation
                    cit = dict(cit, otherCitationDetails=list(cit.get("otherCitationDetails", []))
                               + [f"source {a['codeOrigin'].get('source', '')}"]
                               + ([f"version {a['codeOrigin']['version']}"] if a["codeOrigin"].get("version") is not None else [])
                               + self.origin_details(a["codeOrigin"]))
                o += [f'{J}<mrl:algorithm><mrl:LE_Algorithm id="{self.pid(h, a["id"])}">', f"{J}  <mrl:citation>"] + \
                     self.citation(cit, J + "    ", h) + \
                     [f"{J}  </mrl:citation>", text("mrl:description", a["description"], J + "  "),
                      f"{J}</mrl:LE_Algorithm></mrl:algorithm>"]
            o.append(f"{J}<mrl:identifier>{md_identifier(p['identifier'])}</mrl:identifier>")
            if "softwareReference" in p:
                o += self.wrapped("mrl:softwareReference", p["softwareReference"], J, h)
            if "codeOrigin" in st:                          # 19115-3 allows one softwareReference
                tag = "mrl:documentation" if "softwareReference" in p else "mrl:softwareReference"
                o += self.wrapped(tag, self.origin_citation(st["codeOrigin"]), J, h)
            ctx = st.get("executionContext")                # 0.2: rides runTimeParameters as text
            if ctx is not None:
                both = {"executionContext": ctx}
                if "runTimeParameters" in p:
                    both["parameters"] = p["runTimeParameters"]
                o.append(text("mrl:runTimeParameters", json_text(both), J))
            elif "runTimeParameters" in p:
                o.append(text("mrl:runTimeParameters", json_text(p["runTimeParameters"]), J))
            o.append(f"{I}  </mrl:LE_Processing></mrl:processingInformation>")
        for r in st.get("report", []):
            o += [f"{I}  <mrl:report><mrl:LE_ProcessStepReport>", text("mrl:name", r["name"], I + "    ")]
            if "description" in r:
                o.append(text("mrl:description", json_text(r["description"]), I + "    "))
            o.append(f"{I}  </mrl:LE_ProcessStepReport></mrl:report>")
        for out in st.get("output", []):
            if "sourceCitation" in out:
                o += [f'{I}  <mrl:output><mrl:LE_Source id="{self.pid(h, out["id"])}"><mrl:sourceCitation>'] + \
                     self.citation(out["sourceCitation"], I + "    ", h) + [f"{I}  </mrl:sourceCitation></mrl:LE_Source></mrl:output>"]
            else:
                o.append(f'{I}  <mrl:output><mrl:LE_Source id="{self.pid(h, out["id"])}"/></mrl:output>')
        return o + [f"{I}</mrl:LE_ProcessStep></mrl:processStep>"]
