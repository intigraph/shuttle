"""Published term ownership; independent of deployment/run instance identities.

Crosswalk: https://intigraph.ai/ids/ownership.json
SHA256 a389be53b74259d0c515ff6db16d602474dc5fe38dc6cc47f0f54a2d1347d34e.
Legacy IRIs are read aliases, never a fallback owner for an unknown term.
"""
LEGACY = 'http://aegis.gastown.local/ontology/'
CORE = 'https://w3id.org/intigraph/camayoc/core/ns#'
QUIPU = 'https://w3id.org/intigraph/quipu/ns#'
_OWNERS = {**{name: QUIPU for name in (
    'WorkflowDefinition', 'WorkflowStep', 'WorkflowRun', 'TransitionEvent',
    'VerifierRegistration')}, **{name: CORE for name in (
    'hasStep', 'runOf', 'currentState', 'createdAt', 'sourceKind', 'inRun',
    'atStep', 'fromState', 'toState', 'performedBy', 'signature', 'verifier',
    'attests', 'publicKey')}}
_ALIASES = {LEGACY + name: owner + name for name, owner in _OWNERS.items()}


def term(name: str) -> str:
    return _OWNERS[name] + name


def pattern(subject: str, name: str, obj: str) -> str:
    """Explicit UNION for native readers that drop literals on alternate paths.

    Subject/object are internal SPARQL fragments, never caller text. Keep each
    alternative grouped before joining it to the next required field.
    """
    return (f'{{ {{ {subject} <{term(name)}> {obj} }} UNION '
            f'{{ {subject} <{LEGACY + name}> {obj} }} }}')


def type_filter(variable: str, name: str) -> str:
    return f'FILTER({variable} IN (<{term(name)}>, <{LEGACY + name}>))'


def normalize_fact(row: dict) -> dict:
    """Keep row cardinality and all identity/signature bytes; map known terms only."""
    result = dict(row)
    p = row.get('p')
    if isinstance(p, str):
        result['p'] = _ALIASES.get(p, p)
    if (p == 'http://www.w3.org/1999/02/22-rdf-syntax-ns#type'
            and row.get('iri') is True and isinstance(row.get('value'), str)):
        result['value'] = _ALIASES.get(row['value'], row['value'])
    return result


def prefixes() -> str:
    return f'@prefix core: <{CORE}> .\n@prefix qp: <{QUIPU}> .\n'
