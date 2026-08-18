"""Numeric governance layer (addendum stage A, 治理先行).

From `FELRA_v1.0_未來數值表示與驗證升級附加計畫` §16, stage A:

    不修改數值引擎。
    完成：numeric_policy schema；數值 metadata；後端名稱與版本紀錄；
    source parsing 紀錄；conversion history；證據等級欄位。

So this module records and validates; it computes nothing. Declaring a policy
changes what a run *says about itself*, never what it calculates. The native
Decimal and Rational backends are stage C, and until they exist a policy naming
them is recorded as **declared but not implemented** rather than silently
honoured — a policy that is obeyed only in the manifest is worse than no policy.

Three compatibility rules from §17, all testable:

* **§17.1 default behaviour unchanged** — a project with no `numeric_policy`
  behaves exactly as before, and nothing here runs for it.
* **§17.2 explicit opt-in** — a backend switch requires the declaration.
* **§17.3 / §17.4 fingerprint separation** — a project without a policy keeps its
  existing `result_sha256`; declaring or changing one must change it. That pair is
  the sharp test, because the natural implementation satisfies one and breaks the
  other.

Every vocabulary below is quoted from the addendum rather than invented, and an
unrecognised term is refused rather than passed through. A governance layer that
accepts any string is a free-text field with a schema's reputation.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "EVIDENCE_LEVELS",
    "EVIDENCE_LEVEL_ORDER",
    "SOURCE_PARSING_MODES",
    "CERTIFICATION_MODES",
    "ROUNDING_MODES",
    "NUMERIC_BACKENDS",
    "IMPLEMENTED_BACKENDS",
    "NumericPolicy",
    "NumericPolicyError",
    "describe_numeric_environment",
    "evidence_status",
]


class NumericPolicyError(ValueError):
    """A declared numeric policy is not expressible in the addendum's vocabulary."""


#: §11 證據等級, verbatim. The ladder is ordered; `U` and `F` sit outside it.
EVIDENCE_LEVELS: dict[str, int | None] = {
    "executed": 0,
    "reproduced": 1,
    "precision_stable": 2,
    "cross_backend_consistent": 3,
    "exact_verified": 4,
    "numerically_certified": 5,
    "formally_proved": 6,
    "undetermined": None,
    "falsified": None,
}

#: The ordered rungs only, lowest first.
EVIDENCE_LEVEL_ORDER: tuple[str, ...] = (
    "executed",
    "reproduced",
    "precision_stable",
    "cross_backend_consistent",
    "exact_verified",
    "numerically_certified",
    "formally_proved",
)

#: §6.1 source_parsing
SOURCE_PARSING_MODES = (
    "native",
    "exact_string",
    "rational_pair",
    "symbolic",
    "measured_value",
)

#: §6.2 certification.mode
CERTIFICATION_MODES = (
    "none",
    "stability",
    "cross_backend",
    "interval",
    "ball",
    "formal",
)

ROUNDING_MODES = (
    "nearest_even",
    "nearest_away",
    "toward_zero",
    "toward_positive",
    "toward_negative",
)

#: §4 數值本體註冊表. Naming a backend is allowed before it is implemented — the
#: addendum is explicit that "此表不代表 v1.0 必須一次實作全部後端" — but a
#: declaration of an unimplemented backend must be *reported*, not honoured.
NUMERIC_BACKENDS = ("float64", "decimal", "rational", "binary_mp", "interval", "ball")

#: What this version can actually compute in. Stage A added none by design;
#: stage C (v1.3.0) adds decimal and rational, and this tuple is the ONLY place
#: that claim is made, so `declared_but_not_implemented` cannot drift from it.
IMPLEMENTED_BACKENDS = ("float64", "decimal", "rational")

_ESCALATION_STRATEGIES = ("doubling", "linear", "fixed")


def _require(value: Any, allowed: tuple[str, ...], field_name: str) -> str:
    text = str(value)
    if text not in allowed:
        raise NumericPolicyError(
            "numeric_policy.%s must be one of %s (got %r); the vocabulary is the "
            "addendum's, and an unrecognised term is refused rather than recorded"
            % (field_name, ", ".join(allowed), text)
        )
    return text


@dataclass(frozen=True)
class NumericPolicy:
    """A declared numeric policy. Recorded, validated, and — in stage A — not obeyed."""

    default_backend: str = "float64"
    source_parsing: str = "native"
    working_precision_bits: int | None = None
    target_accuracy_bits: int | None = None
    rounding_mode: str = "nearest_even"
    escalation_enabled: bool = False
    escalation_strategy: str = "doubling"
    max_precision_bits: int | None = None
    cross_backend_enabled: bool = False
    cross_backend_backends: tuple[str, ...] = ()
    certification_mode: str = "none"
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "NumericPolicy | None":
        """Parse a declared policy. Returns None when nothing was declared, which
        is what keeps §17.1 and §17.3 true: an undeclared policy is absent, not
        defaulted, so no fingerprint moves."""
        if not data:
            return None
        if not isinstance(data, dict):
            raise NumericPolicyError("numeric_policy must be a mapping")

        unknown = set(data) - {
            "default_backend", "source_parsing", "working_precision_bits",
            "target_accuracy_bits", "rounding_mode", "escalation",
            "cross_backend", "certification",
        }
        if unknown:
            raise NumericPolicyError(
                "unknown numeric_policy field(s): %s" % ", ".join(sorted(unknown))
            )

        escalation = data.get("escalation") or {}
        cross = data.get("cross_backend") or {}
        certification = data.get("certification") or {}
        for name, value in (("escalation", escalation), ("cross_backend", cross),
                            ("certification", certification)):
            if not isinstance(value, dict):
                raise NumericPolicyError("numeric_policy.%s must be a mapping" % name)

        backends = tuple(str(x) for x in (cross.get("backends") or ()))
        for backend in backends:
            _require(backend, NUMERIC_BACKENDS, "cross_backend.backends")

        def _bits(key: str, source: dict[str, Any]) -> int | None:
            if source.get(key) is None:
                return None
            bits = int(source[key])
            if bits <= 0:
                raise NumericPolicyError("numeric_policy.%s must be positive" % key)
            return bits

        return cls(
            default_backend=_require(
                data.get("default_backend", "float64"), NUMERIC_BACKENDS,
                "default_backend"),
            source_parsing=_require(
                data.get("source_parsing", "native"), SOURCE_PARSING_MODES,
                "source_parsing"),
            working_precision_bits=_bits("working_precision_bits", data),
            target_accuracy_bits=_bits("target_accuracy_bits", data),
            rounding_mode=_require(
                data.get("rounding_mode", "nearest_even"), ROUNDING_MODES,
                "rounding_mode"),
            escalation_enabled=bool(escalation.get("enabled", False)),
            escalation_strategy=_require(
                escalation.get("strategy", "doubling"), _ESCALATION_STRATEGIES,
                "escalation.strategy"),
            max_precision_bits=_bits("max_precision_bits", escalation),
            cross_backend_enabled=bool(cross.get("enabled", False)),
            cross_backend_backends=backends,
            certification_mode=_require(
                certification.get("mode", "none"), CERTIFICATION_MODES,
                "certification.mode"),
            raw=json.loads(json.dumps(data, ensure_ascii=False, sort_keys=True)),
        )

    # -- reporting -------------------------------------------------------

    def declared_but_not_implemented(self) -> list[str]:
        """Everything this policy asks for that this version does not do.

        Stage A implements none of it on purpose. Saying so in the manifest is the
        difference between a governance layer and a decorative one.
        """
        pending: list[str] = []
        if self.default_backend not in IMPLEMENTED_BACKENDS:
            pending.append(
                "default_backend=%s (stage C/D; computation still uses float64)"
                % self.default_backend
            )
        if self.source_parsing != "native":
            pending.append(
                "source_parsing=%s (honoured by `cross_backend` points since "
                "v1.3.0; parameters and datasets elsewhere are still parsed "
                "natively)" % self.source_parsing
            )
        if self.escalation_enabled:
            pending.append("escalation (stage D precision ladder)")
        if self.cross_backend_enabled:
            pending.append("cross_backend consensus (stage D)")
        if self.certification_mode != "none":
            pending.append(
                "certification.mode=%s (stage E, or stage F for `formal`)"
                % self.certification_mode
            )
        if self.working_precision_bits or self.target_accuracy_bits:
            pending.append("precision targets (stage D)")
        return pending

    def digest(self) -> str:
        """Stable digest of the declared policy, so a policy change separates
        fingerprints (§17.4) while an absent policy leaves them untouched (§17.3)."""
        payload = json.dumps(self.raw, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return {
            "declared": self.raw,
            "resolved": {
                "default_backend": self.default_backend,
                "source_parsing": self.source_parsing,
                "working_precision_bits": self.working_precision_bits,
                "target_accuracy_bits": self.target_accuracy_bits,
                "rounding_mode": self.rounding_mode,
                "escalation": {
                    "enabled": self.escalation_enabled,
                    "strategy": self.escalation_strategy,
                    "max_precision_bits": self.max_precision_bits,
                },
                "cross_backend": {
                    "enabled": self.cross_backend_enabled,
                    "backends": list(self.cross_backend_backends),
                },
                "certification": {"mode": self.certification_mode},
            },
            "implemented_backends": list(IMPLEMENTED_BACKENDS),
            "declared_but_not_implemented": self.declared_but_not_implemented(),
            "policy_sha256": self.digest(),
        }


def describe_numeric_environment() -> dict[str, Any]:
    """The numeric environment a run actually happened in.

    §18.1 asks that a run can record its backend, precision and rounding. For
    stage A that is float64 as provided by this interpreter, plus the versions of
    the libraries that would host the later backends, so that a stage-C run can be
    compared against a stage-A one rather than merely succeeding it.
    """
    info: dict[str, Any] = {
        "computation_backend": "float64",
        "float_repr_digits": sys.float_info.dig,
        "float_mant_dig": sys.float_info.mant_dig,
        "float_rounds": sys.float_info.rounds,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
    }
    import decimal

    info["decimal_default_prec"] = decimal.getcontext().prec
    info["decimal_default_rounding"] = decimal.getcontext().rounding
    for module in ("numpy", "sympy", "mpmath"):
        try:
            info[module] = __import__(module).__version__
        except Exception:  # pragma: no cover - reporting only
            info[module] = None
    return info


def evidence_status(
    *,
    executed: bool,
    reproduced: bool | None = None,
    precision_stable: bool | None = None,
    cross_backend_consistent: bool | None = None,
    exact_verified: bool | None = None,
    formal_results: list[dict[str, Any]] | None = None,
    falsified: bool = False,
) -> dict[str, Any]:
    """The §11 evidence ladder for a run.

    Only levels this version can actually establish are ever `pass`. The rest are
    `not_run` — never `not_applicable`, which would claim a judgement this version
    is not entitled to make. `formally_proved` is driven by `formal_check` results
    from v1.1.0, so the two features meet here rather than each inventing a status.
    """
    levels: dict[str, str] = {name: "not_run" for name in EVIDENCE_LEVEL_ORDER}
    levels["executed"] = "pass" if executed else "fail"
    if reproduced is not None:
        levels["reproduced"] = "pass" if reproduced else "fail"
    # A rung is only ever `pass` when something ran and settled it. `None` means
    # nothing addressed it, which stays `not_run` — the ladder must not climb on
    # the absence of a check.
    for name, value in (("precision_stable", precision_stable),
                        ("cross_backend_consistent", cross_backend_consistent),
                        ("exact_verified", exact_verified)):
        if value is not None:
            levels[name] = "pass" if value else "fail"

    formal_results = formal_results or []
    if formal_results:
        verdicts = {r.get("formal_status") for r in formal_results}
        if "refuted" in verdicts:
            levels["formally_proved"] = "fail"
        elif verdicts == {"verified"}:
            levels["formally_proved"] = "pass"
        else:
            # a mix of verified with unknown/unavailable is not a proof
            levels["formally_proved"] = "partial"

    highest: str | None = None
    for name in EVIDENCE_LEVEL_ORDER:
        if levels[name] == "pass":
            highest = name
        else:
            break  # the ladder is cumulative; a gap stops the climb

    status: dict[str, Any] = {
        "highest_level": "falsified" if falsified else (highest or "undetermined"),
        "levels": levels,
        "ladder": list(EVIDENCE_LEVEL_ORDER),
        "note": (
            "the ladder is cumulative: `highest_level` is the tallest rung reached "
            "with no gap below it, so a formal proof recorded above an unrun "
            "precision check does not raise the level"
        ),
    }
    if falsified:
        status["falsified"] = True
    return status
