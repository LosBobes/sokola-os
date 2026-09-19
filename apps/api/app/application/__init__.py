"""The application layer: the only place a request may combine domains.

`app/domains/<x>/` may not import another domain's service, repository, router
or policy — the architecture gate enforces that, and it is what keeps the
modular monolith modular. But some questions genuinely need more than one
domain to answer. M03 §12 names the shape: an *application coordinator* that
"combines M03 School/security, M06 ACTIVE membership and M05 allowed workspace
options without creating an M03→M05 domain dependency".

This package is that coordinator layer. It may import from any domain; no
domain may import from it. That one-way rule is what stops this from becoming
a back door for the coupling the gate exists to prevent, and the gate checks
it.
"""
