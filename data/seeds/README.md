# Seed CVE Records

This directory stores known vulnerability seeds used to derive library-independent vulnerability patterns.

Start by copying `seed-template.json`:

```sh
cp data/seeds/seed-template.json data/seeds/zlib-cve-xxxx-yyyy.json
```

Each seed should describe one known CVE or security fix:

- vulnerable and fixed versions
- fixing commit
- affected file/function
- patch summary
- root cause hypothesis
- source, transform, sink, and missing constraints

For phase 1, prefer small patches with clear dataflow and clear security impact.
