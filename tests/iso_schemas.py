"""Validate exported XML against the ISO 19115-3 XSDs, offline.

The ISO bundle (19115AllNamespaces.zip, unzipped) is expected at .cache/iso-schemas; GML and XLink schemas are
fetched once and kept in .cache/iso-schemas/remote. Callers skip when neither is available."""
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / ".cache" / "iso-schemas"
REMOTE = ROOT / "remote"
DEAD_GML = "http://standards.iso.org/ittf/PubliclyAvailableStandards/ISO_19136_Schemas/"   # 404; same files as OGC's
OGC_GML = "http://schemas.opengis.net/gml/3.2.1/"
_schemas = {}


def available() -> bool:
    return (ROOT / "19115" / "-3" / "mrl" / "2.0" / "mrl.xsd").exists()


def _schema(version: str):
    from lxml import etree

    class Resolver(etree.Resolver):
        def resolve(self, url, pid, ctx):
            if not url.startswith("http"):
                return None
            u = url.replace("https://", "http://").replace(DEAD_GML, OGC_GML)
            if u.startswith("http://standards.iso.org/iso/"):
                return self.resolve_filename(str(ROOT / u[len("http://standards.iso.org/iso/"):]), ctx)
            local = REMOTE / u[len("http://"):]
            if not local.exists():
                local.parent.mkdir(parents=True, exist_ok=True)
                local.write_bytes(urllib.request.urlopen(u, timeout=60).read())
            # base_url stays the remote URL, so relative includes come back through this resolver
            return self.resolve_string(local.read_bytes(), ctx, base_url=u)

    cit = "2.0" if version == "2.0" else "1.0"
    wrap = f"""<schema xmlns="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:x-wrap">
 <import namespace="http://standards.iso.org/iso/19115/-3/mrl/{version}" schemaLocation="http://standards.iso.org/iso/19115/-3/mrl/{version}/mrl.xsd"/>
 <import namespace="http://standards.iso.org/iso/19115/-3/cit/{cit}" schemaLocation="http://standards.iso.org/iso/19115/-3/cit/{cit}/cit.xsd"/>
</schema>"""
    parser = etree.XMLParser()
    parser.resolvers.add(Resolver())
    return etree.XMLSchema(etree.fromstring(wrap.encode(), parser, base_url="http://local/wrap.xsd"))


def errors(xml: str, version: str = "2.0") -> list:
    """Schema errors of ``xml`` (written in the mrl/2.0 namespaces) against 19115-3 ``version``."""
    from lxml import etree
    if version == "1.0":
        xml = xml.replace("/mrl/2.0", "/mrl/1.0").replace("/cit/2.0", "/cit/1.0")
    if version not in _schemas:
        _schemas[version] = _schema(version)
    s = _schemas[version]
    s.validate(etree.fromstring(xml.encode()))
    return [f"{e.line}: {e.message}" for e in s.error_log]
