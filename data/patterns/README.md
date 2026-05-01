# Vulnerability Patterns

This directory stores library-independent vulnerability root-cause patterns.

Patterns should be derived from one or more seed CVEs, but should avoid source-library-specific names where possible.

A useful phase-1 pattern should answer:

- What is the attacker-controlled or externally influenced source?
- What transformation makes it dangerous?
- What sink can turn the bad value into memory corruption, OOB access, DoS, or another impact?
- What constraint was missing before the patch?
- What evidence would prove that a target candidate is actually safe?
