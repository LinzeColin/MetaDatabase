from __future__ import annotations
from collections import defaultdict
from typing import Any

def reconcile_claims(claims:list[dict[str,Any]])->dict[str,Any]:
    groups=defaultdict(list)
    for c in claims:
        key=(c.get('subject'),c.get('predicate'),c.get('horizon'),c.get('as_of'))
        groups[key].append(c)
    consensus=[]; conflicts=[]
    for key,items in groups.items():
        directions={i.get('direction') for i in items}
        roots={i.get('root_evidence_sha256') for i in items if i.get('root_evidence_sha256')}
        payload={'key':key,'claim_count':len(items),'independent_root_count':len(roots),'claims':items}
        (conflicts if len(directions)>1 else consensus).append(payload)
    return {'consensus':consensus,'conflicts':conflicts,'order_invariant':True}
