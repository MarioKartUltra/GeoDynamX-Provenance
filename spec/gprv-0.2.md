# `.gprv` 0.2: a provenance record for printed data

Draft of 2026-10-05, approved by the author the same day. License: CC BY 4.0. The worked records and their
ISO exports are in `spec/examples/`; the `gprv` Python library (`src/gprv/`) implements this spec.

The key words MUST, SHOULD and MAY are used as in RFC 2119.

## 1. Scope

A `.gprv` file records what produced one printed file (a dataset or a figure): the declared start, every step
that fed the printed bytes, and for each step its code, its parameters and its outcome. A record written at a
fork cites its parent record by sha256, so the records of a project form a tree. An assembly packages one
product's branch of that tree for sharing. Every record exports mechanically to ISO 19115-3 lineage XML.

The format defines minted records and assemblies. How an application keeps a live draft of the record while the
user works is the application's business.

## 2. Terms

- **Print:** a fork (a derived dataset written for further work) or an export (a dataset or figure written for
  use elsewhere). Each print mints one record.
- **Record:** the canonical JSON file that describes one print. The sha256 of its bytes is its identity.
- **Step:** a computation whose output is read by another step or written by the print.
- **Component:** a coded method inside a step (an `LE_Algorithm`), named by an in-code identifier.
- **Source:** an input of the record: a declared start, a parent dataset, or a patch to the code.
- **Declared start:** a source with no parent record; its description says what is known about it.
- **Parent record:** the record of the print that wrote a dataset this record reads.
- **Reported step:** a step known only from its producer's description; it carries no code.
- **Assembly:** a product's record together with every ancestor record it cites, as JSON Lines.

## 3. Encoding

- A record is the RFC 8785 canonical form of one JSON object, in UTF-8. The file holds exactly those bytes, with
  no trailing newline, so `sha256sum` of the file is the record hash.
- Values follow the RFC 8785 input rules:
  - no duplicate keys;
  - numbers are IEEE-754 doubles;
  - a non-finite value is written as the string `"NaN"`, `"Infinity"` or `"-Infinity"`;
  - an integer outside ±(2^53 − 1) is written as a string;
  - strings are kept as entered (no Unicode normalization).
- Hashes are sha256, written as 64 lowercase hex characters.
- A directory hash (a `codeOrigin` content hash that covers a directory) is the sha256 of the concatenation,
  over every regular file under the directory in sorted order of its POSIX relative path, of the UTF-8 path,
  a line feed, the file's sha256 in hex, and a line feed. Symbolic links and empty directories count for
  nothing.
- A record sits beside the file it describes, named `<printed file name>.gprv` (`fbm_recon.tif.gprv`). An
  assembly is named `<printed file name>.gprv.jsonl`.
- A record is written once. Changing a saved record changes its hash and breaks every citation of it.
- Writers SHOULD use a maintained RFC 8785 library (in Python, `rfc8785`). Python's `json.dumps` differs from RFC 8785
  in number form, escaping and key order.

## 4. Structure

### 4.1 Mapping rules

1. Each key is the ISO 19115-3 element name, nested as in ISO. The XML property element and its class element
   collapse into one JSON object; `gco:CharacterString` becomes a JSON string.
2. The ISO class is implied by position. Every step is an `LE_ProcessStep`, every output an `LE_Source`; a source
   is an `LE_Source` when it has `processedLevel`, otherwise an `LI_Source`.
3. `id` is the XML `id` attribute (`xs:ID`): an XML name (letter or `_` first), unique in the record.
4. A string where the schema expects an object is a reference to the object with that `id`
   (`xlink:href="#id"`). The referenced object is defined in an earlier step, or earlier in the same list.
5. Everything mandatory in ISO is mandatory here, so the exported XML is valid by construction.
6. Four keys have no ISO element: `gprv` (the format version), `sha256` (allowed on any citation),
   `codeOrigin` (allowed on a step and on a component, §6.1) and `executionContext` (on a step, §6.2).
7. Arrays keep their order, and the order is part of the hash.

### 4.2 Objects

**Record** (`mrl:LI_Lineage`)

| Key | | Content |
|---|---|---|
| `gprv` | 1 | `"0.2"` (a reader accepts `"0.1"` too) |
| `statement` | 1 | one sentence on what was printed |
| `source` | 0..* | sources |
| `processStep` | 1..* | steps in run order; the last is the print step |

**Source** (`mrl:LI_Source` / `mrl:LE_Source`)

| Key | | Content |
|---|---|---|
| `id` | 1 | |
| `description` | 1 | what the source is and what is known about it |
| `sourceCitation` | 0..1 | citation of the dataset (title and `sha256`) or of the publication |
| `sourceMetadata` | 0..* | citation of the parent record (title and `sha256`) |
| `processedLevel` | 0..1 | `{code, codeSpace}`: a vendor product's processing level |
| `scope` | 0..1 | `{"level": "software"}` on a patch source; other uses are reserved |

**Step** (`mrl:LE_ProcessStep`)

| Key | | Content |
|---|---|---|
| `id` | 1 | |
| `description` | 1 | |
| `stepDateTime` | 0..1 | RFC 3339 UTC instant; on the print step only |
| `reference` | 0..* | citations of the method a reported step names |
| `source` | 0..* | ids of the sources and earlier outputs this step reads |
| `processingInformation` | 0..1 | the code that ran; absent on a reported step |
| `report` | 0..* | `{name, description}`; `name` = `outcome` for the outcome (§5.6) |
| `output` | 0..* | `{id, sourceCitation}`; the citation (title and `sha256`) only when the output is a file |
| `codeOrigin` | 0..1 | where the step's code came from, when the commit form of §6 cannot name it (§6.1) |
| `executionContext` | 0..1 | how the step ran: precision, backend, libraries, platform, third-party components (§6.2) |

**Processing** (`mrl:LE_Processing`)

| Key | | Content |
|---|---|---|
| `algorithm` | 0..* | components in run order, each an object or the `id` of one defined earlier |
| `identifier` | 1 | `{code, codeSpace}`: the step's in-code identifier (§6) |
| `softwareReference` | 0..1 | citation of the code base (§6), or the `id` of one defined earlier |
| `runTimeParameters` | 0..1 | object (§5.4) |

**Component** (`mrl:LE_Algorithm`): `id` (1), `description` (1), `citation` (1), `codeOrigin` (0..1, §6.1).

**Code origin** (no ISO element; §6.1)

| Key | | Content |
|---|---|---|
| `kind` | 1 | `repository`, `package`, `file`, `archive`, `service` or `other` |
| `source` | 1 | a URI: a repository URL with its commit (`git+https://…@<commit>`), a package spec (`pypi:name==1.2.0`, `conda:…`, `npm:…`), a `file:` path relative to a root the writer declares, an archive URL, a service endpoint |
| `name` | 1 | what the code calls itself |
| `version` | 0..1 | the source's own version string; `null` when it has none |
| `contentHash` | 1 | `{algorithm, value, covers}`: `algorithm` `sha256` (64 hex) or `sha1` (40 hex); `covers` `file`, `directory`, `distribution` or `none` (no `value`; a service or a repository only) |
| `license` | 1 | an SPDX licence expression, or `NOASSERTION` |
| `citation` | 0..1 | free text or a DOI |
| `editable` | 0..1 | `true` when the version may stay while the content changes (an editable install): the hash, not the version, is then authoritative |

**Citation** (`cit:CI_Citation`): `title` (1), `edition` (0..1), `identifier` (0..*, `{code, codeSpace}`),
`otherCitationDetails` (0..*, strings), `onlineResource` (0..*, `{linkage}`), `sha256` (0..1), `id` (0..1).

## 5. What a record contains

### 5.1 Only what produced the print

A record is computed from the printed output's dependency set at print time: the steps, components and
parameters whose values the printed bytes depend on. Session history, undo logs, cache contents and the state of
unused tools are never inputs to the writer.

Property (history independence): the same print reached through two different editing histories gives the same
record, apart from the print step's `stepDateTime`. An application tests it by printing, adding and removing a
step, changing a setting the output does not read, and printing again; the records match.

### 5.2 Steps

- A step ends where its output is read by another step or written by the print. A selection (a threshold over
  measured objects that keeps a subset) is a step: its parameters are the predicate, its output the kept subset.
- A step that has no sources is allowed. A generated input (random generator and seed, spectral shaping, inverse
  FFT) is a chain of such steps.
- Steps are listed in run order; a step comes after every step whose output it reads.

### 5.3 Components

- Each component carries its in-code identifier in `citation.identifier` (§6). A DOI of the defining paper MAY
  follow as a second identifier with `codeSpace` `doi`.
- A component used by several steps is written once and referenced by `id` afterwards.
- Code the writer cannot pin by commit (a numerical backend, a renderer, a library, a remote service) is a
  component cited by `title` and `edition`; from 0.2 the component may also carry a `codeOrigin` (§6.1) that
  says, checkably, where that code came from.
- The numerical backend is part of the method. A step that calls an FFT names the backend as a component with
  its version; its precision, and for FFTW the planner mode, go in that component's parameters. FFTW output is
  repeatable only with `FFTW_ESTIMATE` or saved plans (FFTW FAQ Q3.8).

### 5.4 Parameters

- `runTimeParameters` groups parameters under the `id` of the component that reads them:
  `{"w2": {"kappa": 1, "clip": false}}`. A key that is not a component `id` belongs to the step.
- Names and values are the application's own, so replay can feed them back.
- Values are stored parsed. A parameter that is itself structured is a JSON object, never JSON text inside a
  string.
- Inactive parameters are left out (a tolerance whose check is off).
- A filter at its pass-all setting is left out entirely. Each filter declares its pass-all condition.

### 5.5 Loops

- A loop inside one step is described by its components: the repeating body is one component, the stop rule
  another (its cap and tolerance are its parameters), and the outcome records the iterations run, the stop reason
  and the iterate returned.
- A plain fixed count is a parameter of the repeating component.
- A loop is unrolled into steps only when an iterate becomes data (kept, printed, or read by another step) or the
  body changes between iterations.
- A run resumed from a cached state is one loop; the outcome holds the total iteration count.

### 5.6 Outcome

- The outcome is the `report` entry named `outcome`. Its `description` is an object grouped by component `id`,
  like the parameters; keys that are not component ids belong to the step.
- The code owns the field list. An iterative component reports the iterate it returned (`returned`).
- Per-iterate trajectories are left out; replay regenerates them.
- A reported step MAY carry an outcome as a plain string, such as a producer's stated accuracy.
- The outcome is inside the record hash. Verifying a step means replaying it and comparing the outcome and the
  output sha256.

### 5.7 The print step

- The print step is the last step. It carries `stepDateTime`, and each of its outputs cites the written file by
  base name and sha256.
- A figure's print step is a render step: the renderer is a component with its version, and the view settings
  (colormap, stretch, extent, labels, DPI) are its parameters.
- An application SHOULD keep wall-clock times out of the printed bytes, so a replayed print can be compared by
  sha256. The record's `stepDateTime` holds the time.

## 6. Code identity

- **The commit.** `softwareReference` cites the code base: `title`, `edition` = the full git commit hash,
  `onlineResource` = the repository URL, and `otherCitationDetails` = the interpreter and library versions that can
  change the output (`"python 3.12.13"`, `"numpy 2.4.3"`; a numpy `Generator` stream is not fixed across numpy
  versions by its seed alone, NEP 19). A code base installed without git gives its release version as `edition`.
- **The in-code identifier.** A tag in a comment, on or directly above the definition it names:

  ```python
  # gprv: mz_lastwave.w2_interp
  def interp(...):
  ```

  The same form works in any language (`% gprv: …` in MATLAB, `// gprv: …` in C). A name uses lowercase letters,
  digits and `_ . / -`, and appears exactly once in the repository at the cited commit, so
  `git grep -n "gprv: mz_lastwave.w2_interp" <commit>` finds the code. A tag survives renames of the function it
  marks. Step identifiers (`LE_Processing.identifier`, such as `mz_edges/recon`) are tags too.
- **The codeSpace** of a tag is the project name (`geodynamix`). The step's `softwareReference` says which
  repository and commit the tag resolves in.
- **Uncommitted changes.** When the working tree differs from the commit, the writer saves the difference beside
  the record as a patch that `git apply` turns the commit into the working tree, untracked source files included.
  The patch is a source with `scope` `{"level": "software"}` and a `sourceCitation` with its file name and sha256.
  Every step whose code came from that tree lists the patch in its `source`. Replay = the commit plus the patch.

### 6.1 Code origin

- The commit form above stays the default and the fallback. `codeOrigin` covers code that form cannot name: a
  file in a user folder, an installed package, a script, an archive, a remote service. It sits on a step (the
  code that ran the step) or on a component (one piece the step used); a writer may emit both the commit form
  and a `codeOrigin`.
- `contentHash.covers` says what was hashed, so a reader knows a single-file hash does not cover what that
  file imports: `file` (the file's bytes), `directory` (§3's directory hash), `distribution` (the installed
  distribution's archive or record), `none` (a service, or a repository the commit alone names).
- A reader checks the record (§9). With the code at hand, `gprv verify --code-root <dir>` recomputes a
  `file:` origin's hash under that root and reports a match, a mismatch, or that the code is unavailable.
- `gprv migrate` rewrites a 0.1 record whose `softwareReference` carries a repository URL and a full commit
  into a 0.2 record with a `codeOrigin` of kind `repository` on each such step. It adds nothing it cannot
  derive, writes a new record (the original stays verifiable), and leaves everything else as it was.

### 6.2 Execution context

A step may say how it ran, beside what ran it. The 0.1 forms stay valid (§5.3: the FFT backend as a component
with its version, precision and planner mode in its parameters; §6: interpreter and library versions as text in
`softwareReference.otherCitationDetails`); a writer may emit them and this block together.

```json
"executionContext": {
  "precision": "float32",
  "backend": {"name": "fftw", "version": "3.3.10", "planner": "FFTW_ESTIMATE", "binding": "pyfftw 0.14.0"},
  "fallback": "mlx has no double FFT; using FFTW3 double",
  "libraries": {"python": "3.12.7", "numpy": "2.1.3", "numba": "0.60.0", "mlx": null},
  "platform": "macOS-14.5-arm64",
  "thirdParty": [{"component": "tj"}]
}
```

| Key | | Content |
|---|---|---|
| `precision` | 0..1 | `float32` or `float64`, the precision the step computed in |
| `backend` | 0..1 | `{name, version, planner, binding}`; `name` (1) is `fftw`, `mlx`, `cuda` or `numpy`, the rest text or null |
| `fallback` | 0..1 | text: why the step ran on another backend or precision than asked |
| `libraries` | 0..1 | library name → version text, or null for one that was not loaded; any names |
| `platform` | 0..1 | text: the operating system and architecture |
| `thirdParty` | 0..* | `{component}`: a component of this step (defined in it or referenced by it) whose `codeOrigin` (§6.1) carries the third-party code's origin, version, licence and citation |

The block sits on the step it describes, one per step. It has no ISO element (§4.1 rule 6); the export
writes it as text (§10).

## 7. Starts and parents

- **Declared start.** A source without `sourceMetadata`. Its `description` begins with what is known. Its
  `sourceCitation` holds the file (base name and sha256) or the publication that describes the data
  (title and DOI). A vendor product gives its processing level in `processedLevel` (e.g. ASTER `PROCESSINGLEVELID`).
- **Parent dataset.** A source whose `sourceCitation` holds the dataset's base name and sha256 and whose
  `sourceMetadata` cites the parent record by base name and sha256. The writer finds the parent record in the
  sidecar `<dataset>.gprv` and checks that the sidecar's print step output has the dataset's sha256 before citing it.
- **Reported steps.** A producer's described processing is written as steps without `processingInformation`:
  `description` states what the producer reported (starting `Reported:`), `reference` cites a named method, and the
  last reported step's output cites the downloaded file by sha256. Manual work and confidential inputs are said in
  the description; a vocabulary for how a value was known comes in 0.2 (§11).

## 8. Assemblies

### 8.1 Form

- One line per member record: the member's exact bytes followed by LF. A canonical record contains no LF byte
  (RFC 8785 emits no whitespace between tokens and writes U+000A inside strings as `\n`), so the sha256 of each
  line is the member's hash.
- Lines are sorted by member hash, with no duplicates. The same members give the same bytes in any input order.
- The members are the product's record and every ancestor it cites, as far as the publisher holds them. Sibling
  branches stay out.
- An assembly is written when a product is published or shared. It states nothing of its own: no time, no sink
  field. Anchoring its hash anchors every member.

### 8.2 Verification

An assembly verifies when:
1. every line is canonical (RFC 8785 of its parse equals its bytes);
2. lines are sorted by hash, with no duplicates;
3. every member passes the record checks (§9);
4. for every parent citation that resolves to a member, the dataset sha256 in the citing source equals the sha256
   of an output of that member;
5. exactly one member (the sink) is cited by no other member.

A citation that resolves to no member is a **gap**. Gaps are reported and allowed: an ancestor can be withheld
(confidential data, a private location), and the citation still commits to its bytes, so it can be disclosed and
checked later.

### 8.3 Branches

Several methods applied to one parent are several children citing one parent hash. Re-running the parent with a
changed method mints a new parent record; earlier children keep citing the earlier parent and still verify. A
product that compares branches (the difference of two reconstructions) has one source per branch, and its
assembly holds both branches with the shared parent once.

## 9. Record checks

A record verifies when:
- its bytes are canonical, and the version is one the verifier knows;
- every mandatory key is present and every `id` is an XML name, unique in the record;
- every string reference resolves to an object defined earlier in the record, and every step `source` names a
  source or an output of an earlier step;
- the last step carries `stepDateTime`, and its outputs carry `sha256`;
- every `codeOrigin` has a known `kind`, a `source` that is a URI, a `contentHash` whose algorithm is known
  and whose value has that algorithm's length (or covers nothing, on a service or repository origin), and a
  `license` that is an SPDX expression or `NOASSERTION`;
- every `executionContext` holds only the keys of §6.2 and at least one, a known `precision` and backend
  `name`, versions as text or null, and `thirdParty` entries that each name a component of that step carrying a
  `codeOrigin`.

A verifier reports the versions of the records it checked. With the files at hand, it also checks the sha256
of every cited file. Replay is a separate tool.

## 10. ISO 19115-3 export

- The export is one `mrl:LI_Lineage` in the namespaces `mrl/2.0`, `cit/2.0`, `mcc/1.0`, `gco/1.0` and GML 3.2. The
  same document with the `mrl/1.0` and `cit/1.0` namespaces validates against 19115-3 version 1.0.
- An assembly exports flat. Every member's sources and steps go at the top level, and every `id` becomes
  `r` + the first 12 hex characters of the member hash + `.` + the local id. The exporter checks that the
  resulting ids are unique. A single record exports as an assembly of one.
- Elements are written in schema order: in a step, the `LI_ProcessStep` elements (`description`, `stepDateTime`,
  `reference`, `source`) before the `LE_ProcessStep` ones (`processingInformation`, `report`, `output`); in
  `LE_Processing`, `algorithm` before `identifier`.
- Crossings:

  | `.gprv` | ISO |
  |---|---|
  | `sha256` on a citation | `cit:identifier/mcc:MD_Identifier`, `codeSpace` = `sha256` |
  | `runTimeParameters`, an object `report.description` | its RFC 8785 text in a `gco:CharacterString` |
  | `stepDateTime` | `gml:TimeInstant`, with a minted `gml:id` |
  | `scope.level` | `mcc:MD_Scope/mcc:level/mcc:MD_ScopeCode` with the ISO codelist URL |
  | a resolved parent citation | `LI_Source/sourceStep` → the parent step that output the dataset |
  | the sink's `statement` | `mrl:statement` |
  | the assembly file | `additionalDocumentation`, with its sha256 |
  | a step's `codeOrigin` | a citation with `title` = `name`, `edition` = `version`, `onlineResource` = `source`, `otherCitationDetails` = the kind, the hash and the licence as text: `mrl:softwareReference` when the step cites no code base, else `mrl:documentation` (19115-3 allows one software reference) |
  | a component's `codeOrigin` | `otherCitationDetails` on the component's citation: source, version, hash and licence as text |
  | a step's `executionContext` | its RFC 8785 text in `LE_Processing.runTimeParameters` as `{"executionContext": …, "parameters": …}`, the step's own parameters under `parameters`; a step without the block exports its parameters as in 0.1 |

- What the export loses: the `gprv` version, the ancestors' statements (`LI_Lineage` holds one), parameter
  types, the meaning of the hashes (ISO tools see opaque identifiers), and the structure of a `codeOrigin`
  (its kind, what the hash covers and the `editable` flag survive only as text), the structure of an
  `executionContext` (text only), and an `executionContext` on a step without `processingInformation` (there is
  no `LE_Processing` to carry it). Member boundaries survive as id prefixes and member hashes as the
  `sourceMetadata` citations.

## 11. Privacy and network

- No writer or verifier contacts a network service unless the user asks to anchor an export; the application then
  states what is sent.
- A record holds no personal data by default: base file names, no user names, host names or absolute paths, and
  no person unless the user enters one.

## 12. Later versions

- **0.2** (this version) adds `codeOrigin` (§6.1) and `executionContext` (§6.2). Still to come under 0.2: the
  location block (camera position, feature position, orientation, each with how it was known:
  `device`, `derived`, `manual`, `reported`, `unknown`) on `scope`, and advisory records that flag a component's
  code range as wrong (OSV git ranges).
- Anchoring: an OpenTimestamps proof beside the anchored file (`<file>.ots`); a record never contains its own proof.
- Replay, the methods generator, an ISO 19157 quality export, the ε-agreement between backends, a W3C PROV export,
  workflow-level loops.
- A JSON Schema ships with the library.

## 13. Writers

Three ways to write the same format:
1. **Wrap:** `gprv run --in … --out … -- <command>` mints one step for an unmodified script: the script, the
   commit and patch, the arguments, the environment and the hashes of the declared inputs and outputs.
2. **Annotate:** `gprv:` tags on methods plus a small library call that records components, parameters, sources
   and outcomes.
3. **Integrate:** an application (GeoDynamix) mints at fork and export from its own resolved recipe.

The library and CLI (`verify` with `--code-root`, `show`, `assemble`, `export`, `migrate`; `run` to come) are MIT-licensed; GeoDynamix stays
GPL-2.0-or-later.

## Appendix A: worked example

Built by `spec/examples/build.py` with the `gprv` library and checked by its tests. Dataset hashes are stand-ins
(sha256 of `stand-in <name>`); record and assembly hashes are the real sha256 of the files. The identifier tags
are illustrative and the outcome numbers made up. The ISO exports validate against `mrl/2.0` and `mrl/1.0`.

| File | sha256 (first 12) | Content |
|---|---|---|
| `fbm_roi.npz.gprv` | `8f51734f67ac` | parent: declared start, ROI window, fork |
| `fbm_recon.tif.gprv` | `ab464d3337bb` | child: edges, reconstruction, GeoTIFF export |
| `fbm_recon.png.gprv` | `a3656abec0d9` | sibling: the same chain from a patched tree, rendered |
| `boem_roi.npz.gprv` | `703ec3d3b576` | six reported BOEM steps, then a GeoDynamix window and fork |
| `fbm_recon.tif.gprv.jsonl` | `a2fe1db326fb` | assembly of the parent and the child: VERIFIED |
| `code_origin.npz.gprv` | `d8b871bcc76b` | 0.2: one `codeOrigin` of every kind, on steps and components |
| `exec_context.tif.gprv` | `92ee8c1373ca` | 0.2: the child rewritten with an `executionContext` on every step; the LastWave bank a third-party component with its `codeOrigin` |

The negative cases give: the parent and both children with no product, FAILED (2 sinks); the parent edited
(`x0` 256 → 257), FAILED (2 sinks, one gap); the child alone, VERIFIED with one gap.

Parent, pretty-printed (on disk it is one canonical line):

```json
{"gprv": "0.1",
 "statement": "A 512x512 window of a synthetic fBm field, forked to a derived dataset.",
 "source": [
   {"id": "s1", "description": "Declared start: synthetic 2-D fBm, H=0.7, 1024x1024, spectral synthesis, seed 42.",
    "sourceCitation": {"title": "fbm_H0.7_1024.npz", "sha256": "c2b082442efa2a3869033fd252bf6da2c181bc03c7660010e488ffb6bba23db8"}}],
 "processStep": [
   {"id": "p1", "description": "ROI window, 512x512 from (256, 256).",
    "source": ["s1"], "output": [{"id": "d1"}],
    "processingInformation": {
      "identifier": {"code": "roi/window", "codeSpace": "geodynamix"},
      "softwareReference": {"id": "gdx", "title": "GeoDynamix", "edition": "6194b86e5859cf5a4a0d68f8425b8ac8d86d2df8",
                            "otherCitationDetails": ["python 3.12.13", "numpy 2.4.3"],
                            "onlineResource": [{"linkage": "https://github.com/MarioKartUltra/GeoDynamX"}]},
      "runTimeParameters": {"height": 512, "width": 512, "x0": 256, "y0": 256}}},
   {"id": "p2", "description": "Fork: the window written as a derived dataset.",
    "stepDateTime": "2026-10-01T16:05:12Z",
    "source": ["d1"],
    "output": [{"id": "o1", "sourceCitation": {"title": "fbm_roi.npz", "sha256": "5ef928efdec603cb6df541fb750261950914c6077651e2be811285d0b4ee9991"}}],
    "processingInformation": {
      "identifier": {"code": "fork", "codeSpace": "geodynamix"},
      "softwareReference": "gdx",
      "runTimeParameters": {"bands": ["field"]}}}]}
```

Child, pretty-printed:

```json
{"gprv": "0.1",
 "statement": "LastWave reconstruction of the forked fBm window from its modulus maxima, exported to GeoTIFF.",
 "source": [
   {"id": "s1", "description": "The forked dataset fbm_roi.npz.",
    "sourceCitation": {"title": "fbm_roi.npz", "sha256": "5ef928efdec603cb6df541fb750261950914c6077651e2be811285d0b4ee9991"},
    "sourceMetadata": [{"title": "fbm_roi.npz.gprv", "sha256": "8f51734f67ac9486eb9bd40465c5bad006f023aeddead94c5c8132ddeabfd9c9"}]}],
 "processStep": [
   {"id": "p1", "description": "Dyadic wavelet modulus maxima, LastWave dwtrans2d port, J=4, mirror border.",
    "source": ["s1"], "output": [{"id": "d1"}],
    "processingInformation": {
      "algorithm": [
        {"id": "lw_bank", "description": "FIR analysis/synthesis bank, bit for bit with LastWave convol2.c",
         "citation": {"title": "LastWave FIR bank", "identifier": [{"code": "mz_lastwave.fir_bank", "codeSpace": "geodynamix"}]}},
        {"id": "ext2", "description": "modulus maxima detection, LastWave extrema2",
         "citation": {"title": "extrema2", "identifier": [{"code": "mz_lastwave.extrema2", "codeSpace": "geodynamix"},
                                                          {"code": "10.1109/34.142909", "codeSpace": "doi"}]}}],
      "identifier": {"code": "mz_edges/edges", "codeSpace": "geodynamix"},
      "softwareReference": {"id": "gdx", "title": "GeoDynamix", "edition": "6194b86e5859cf5a4a0d68f8425b8ac8d86d2df8",
                            "otherCitationDetails": ["python 3.12.13", "numpy 2.4.3"],
                            "onlineResource": [{"linkage": "https://github.com/MarioKartUltra/GeoDynamX"}]},
      "runTimeParameters": {"lw_bank": {"border": "mirror", "n_levels": 4}}}},
   {"id": "p2", "description": "Reconstruction from all maxima: LastWave alternating projections, run to convergence.",
    "source": ["d1"], "output": [{"id": "d2"}],
    "processingInformation": {
      "algorithm": ["lw_bank",
        {"id": "lw_proj", "description": "alternating projections, LastWave ext2_proj.c",
         "citation": {"title": "Alternating projections", "identifier": [{"code": "mz_lastwave.ext2_proj", "codeSpace": "geodynamix"}]}},
        {"id": "w2", "description": "P_Gamma: W2_interp sinh interpolation between anchors",
         "citation": {"title": "W2_interp", "identifier": [{"code": "mz_lastwave.w2_interp", "codeSpace": "geodynamix"}]}},
        {"id": "stop", "description": "stop at relative change < tolerance, residual rising 3 times running, or the cap",
         "citation": {"title": "Converge stop rule", "identifier": [{"code": "mz_lastwave.converge_stop", "codeSpace": "geodynamix"}]}}],
      "identifier": {"code": "mz_edges/recon", "codeSpace": "geodynamix"},
      "softwareReference": "gdx",
      "runTimeParameters": {"stop": {"iterations": 20, "run_mode": "converge", "tolerance": 0.001},
                            "w2": {"clip": false, "kappa": 1}}},
    "report": [{"name": "outcome", "description": {"lw_proj": {"residual": 0.0097}, "snr_db": 29.1,
                                                  "stop": {"iterations": 12, "reason": "converged", "returned": 12}}}]},
   {"id": "p3", "description": "Export to GeoTIFF.",
    "stepDateTime": "2026-10-01T16:41:07Z",
    "source": ["d2"],
    "output": [{"id": "o1", "sourceCitation": {"title": "fbm_recon.tif", "sha256": "981ea82a0b40bf14f4b13ae5cd1cdc7cdb80ebf635db362cbbb42c67f2c9e398"}}],
    "processingInformation": {
      "identifier": {"code": "export/geotiff", "codeSpace": "geodynamix"},
      "softwareReference": "gdx",
      "runTimeParameters": {"compress": "deflate", "dtype": "float32", "nodata": "NaN"}}}]}
```

The BOEM record's switch from reported steps to recorded ones (excerpt of `boem_roi.npz.gprv`):

```json
{"id": "p3", "description": "Reported: seams shifted by hand, +/-10-20 ms two-way time (seasonal Loop Current velocities). Manual.",
 "source": ["r2"], "output": [{"id": "r3"}]},
{"id": "p4", "description": "Reported: two-way time in ms x 0.0005 to one-way seconds, then the 7th-order time-to-depth polynomial; depth in ft.",
 "reference": [{"title": "Advocate and Hood 1993, Geo-Marine Letters 13, 207-211"}],
 "source": ["r3"], "output": [{"id": "r4"}]},
…
{"id": "p6", "description": "Reported: exported from ArcMap as GeoTIFF; downloaded from the BOEM product page.",
 "source": ["r5"],
 "output": [{"id": "r6", "sourceCitation": {"title": "BOEMbathyW_ft.tif", "sha256": "3e7450dea4f9329b0725aef7c25cddbac0906e0a2ad70351630ddb82a3b28b79"}}]},
{"id": "p7", "description": "ROI window, 4096x4096 from (20000, 12000).",
 "source": ["r6"], "output": [{"id": "d1"}],
 "processingInformation": {"identifier": {"code": "roi/window", "codeSpace": "geodynamix"}, "softwareReference": {…}, …}}
```

## Appendix B: choices made in this draft

The defaults the author accepted on 2026-10-05 are written in as decided. These further choices were made while
writing; the author accepted them the same day:

1. The version key is `gprv` (it was `prov`), value `"0.1"`.
2. `statement` is required (ISO allows 0..1); the assembly export takes the sink's.
3. The print step is the last step and the only one with `stepDateTime`.
4. A reported step is a step without `processingInformation`; manual work and confidential inputs are stated in
   its description until 0.2 adds the how-known vocabulary.
5. `reference` (`LI_ProcessStep/reference`) joins the profile, so a reported step can cite the method it names.
   Its placement was validated against `mrl/2.0` and `mrl/1.0`, with a misplaced `reference` as a negative control.
6. Step identifiers are `gprv:` tags too, and a tag name is unique in its repository.
7. A patch covers untracked source files, and every step whose code came from the dirty tree lists it.
8. An object referenced by `id` is defined earlier in the record.
9. A reported outcome may be a plain string.
10. Applications keep wall-clock times out of printed bytes (for GeoDynamix: the `forked` time in a derived
    `.npz` moves to the record's `stepDateTime`).
11. The profile is closed: a key outside §4.2 is a problem. The JSON Schema (`src/gprv/schema/gprv-0.1.schema.json`)
    covers structure; the checks of §9 are the full test.
