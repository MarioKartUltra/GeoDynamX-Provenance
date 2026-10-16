# gprv

`.gprv` records exactly what produced a dataset or figure: the declared start, every step that fed the printed
bytes, and for each step its code (in-code identifier and git commit), its parameters and its outcome. Records are
canonical JSON (RFC 8785) keyed by ISO 19115-3 lineage names; a record written at a fork cites its parent by
sha256, and an assembly packages one product's branch for sharing.

- The format: [`spec/gprv-0.2.md`](spec/gprv-0.2.md) (0.2 adds a step's code origin and execution context;
  a reader accepts 0.1 records, [`spec/gprv-0.1.md`](spec/gprv-0.1.md)); worked records in
  [`spec/examples/`](spec/examples/).
- The library: [`src/gprv/`](src/gprv/), with its tests in [`tests/`](tests/).

## The library

```sh
pip install -e .            # Python 3.10+, depends on rfc8785
pip install -e ".[test]"    # pytest, jsonschema, lxml, numpy
```

```python
import gprv

h = gprv.write("fbm_recon.tif.gprv", record)    # value rules, record checks, canonical bytes, written once
problems = gprv.check(open("fbm_recon.tif.gprv", "rb").read())
members, gaps = gprv.collect(product_bytes, gprv.load_store(["records/"]))
blob = gprv.assemble(members)                   # <product>.gprv.jsonl
result = gprv.verify(blob)                      # .ok, .sink, .gaps, .problems
xml = gprv.export(blob, "fbm_recon.tif.gprv.jsonl")
```

```sh
gprv verify fbm_recon.tif.gprv          # record, its ancestors beside it, and every cited file found there
gprv assemble fbm_recon.tif.gprv        # writes fbm_recon.tif.gprv.jsonl
gprv export fbm_recon.tif.gprv.jsonl -o lineage.xml
gprv show fbm_recon.tif.gprv
```

The ISO schema tests run offline against `.cache/iso-schemas` (the unzipped `19115AllNamespaces.zip` from
standards.iso.org); GML and XLink schemas are fetched once into `.cache/iso-schemas/remote`. Without the bundle
those tests are skipped.

## License

The library code is MIT (`LICENSE`). The specs, `spec/gprv-0.1.md` and `spec/gprv-0.2.md`, are CC BY 4.0.
